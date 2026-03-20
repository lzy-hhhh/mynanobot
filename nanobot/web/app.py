"""nanobot Web API - FastAPI application."""

import json
import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from nanobot.config.loader import load_config, get_config_path
from nanobot.config.paths import get_workspace_path, get_cron_dir
from nanobot.bus.queue import MessageBus
from nanobot.session.manager import SessionManager
from nanobot.cron.service import CronService
from nanobot.heartbeat.service import HeartbeatService


class AppState:
    """Application state holder."""
    config: Any = None
    bus: MessageBus = None
    sessions: SessionManager = None
    cron: CronService = None
    heartbeat: HeartbeatService = None
    agent: Any = None
    channels: Any = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="nanobot Web API",
        description="Web interface for nanobot personal AI assistant",
        version="0.1.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize state
    state = AppState()
    app.state = state

    # Initialize on startup
    @app.on_event("startup")
    async def startup():
        nonlocal state
        state.config = load_config()
        state.bus = MessageBus()
        state.sessions = SessionManager(state.config.workspace_path)

        # Create cron service (on_job callback will be set after agent is created)
        cron_store_path = get_cron_dir() / "jobs.json"
        state.cron = CronService(cron_store_path)
        await state.cron.start()

        print("[web] FastAPI server started")

    # Register routes
    register_routes(app, state)

    return app


def register_routes(app: FastAPI, state: AppState):
    """Register all API routes."""

    # ========================================================================
    # Static Files & Frontend
    # ========================================================================

    @app.get("/")
    async def index():
        """Serve the main frontend page."""
        web_dir = Path(__file__).parent
        static_dir = web_dir / "static"
        index_file = static_dir / "index.html"

        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse("<h1>nanobot Web UI</h1><p>Frontend not built yet.</p>")

    # ========================================================================
    # System Status
    # ========================================================================

    @app.get("/api/status")
    async def get_status():
        """Get system status."""
        from nanobot.providers.registry import PROVIDERS

        config = state.config
        providers_status = {}

        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                providers_status[spec.name] = {"status": "oauth", "configured": True}
            elif spec.is_local:
                providers_status[spec.name] = {
                    "status": "local",
                    "configured": bool(p.api_base),
                    "api_base": p.api_base
                }
            else:
                providers_status[spec.name] = {
                    "status": "api_key",
                    "configured": bool(p.api_key)
                }

        channels_status = {}
        for name, cls in state.config.channels.__dict__.items():
            if isinstance(cls, dict):
                channels_status[name] = {"enabled": cls.get("enabled", False)}
            elif hasattr(cls, "enabled"):
                channels_status[name] = {"enabled": cls.enabled}

        cron_status = state.cron.status() if state.cron else {"jobs": 0}

        return {
            "version": "0.1.4",
            "workspace": str(config.workspace_path),
            "model": config.agents.defaults.model,
            "providers": providers_status,
            "channels": channels_status,
            "cron": cron_status,
            "heartbeat": {
                "enabled": config.gateway.heartbeat.enabled,
                "interval_s": config.gateway.heartbeat.interval_s
            }
        }

    # ========================================================================
    # Config Management
    # ========================================================================

    @app.get("/api/config")
    async def get_config():
        """Get current configuration."""
        config = state.config
        return {
            "agents": {
                "defaults": {
                    "model": config.agents.defaults.model,
                    "temperature": config.agents.defaults.temperature,
                    "max_tokens": config.agents.defaults.max_tokens,
                    "context_window_tokens": config.agents.defaults.context_window_tokens,
                    "max_tool_iterations": config.agents.defaults.max_tool_iterations,
                    "workspace": str(config.agents.defaults.workspace),
                }
            },
            "gateway": {
                "port": config.gateway.port,
                "heartbeat": {
                    "enabled": config.gateway.heartbeat.enabled,
                    "interval_s": config.gateway.heartbeat.interval_s
                }
            },
            "channels": config.channels.dict() if hasattr(config.channels, "dict") else {},
        }

    @app.post("/api/config")
    async def update_config(request: Request):
        """Update configuration."""
        # For now, just return the current config
        # Full config update would require writing to config file
        return {"status": "ok", "message": "Config update not yet implemented"}

    # ========================================================================
    # Channel Management
    # ========================================================================

    @app.get("/api/channels")
    async def get_channels():
        """Get all channels status."""
        from nanobot.channels.registry import discover_all

        config = state.config
        all_channels = discover_all()
        result = []

        for name, cls in sorted(all_channels.items()):
            section = getattr(config.channels, name, None)
            if section is None:
                enabled = False
            elif isinstance(section, dict):
                enabled = section.get("enabled", False)
            else:
                enabled = getattr(section, "enabled", False)

            result.append({
                "name": name,
                "display_name": cls.display_name,
                "enabled": enabled,
                "config": section if isinstance(section, dict) else {}
            })

        return {"channels": result}

    @app.post("/api/channels/{channel_name}")
    async def toggle_channel(channel_name: str, request: Request):
        """Enable or disable a channel."""
        body = await request.json()
        enabled = body.get("enabled", False)

        # Update config file
        from nanobot.config.loader import get_config_path, save_config

        config_path = get_config_path()
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "channels" not in data:
            data["channels"] = {}

        if channel_name not in data["channels"]:
            data["channels"][channel_name] = {"enabled": False}

        if isinstance(data["channels"][channel_name], dict):
            data["channels"][channel_name]["enabled"] = enabled
        else:
            data["channels"][channel_name] = {"enabled": enabled}

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Reload config
        state.config = load_config()

        return {"status": "ok", "channel": channel_name, "enabled": enabled}

    # ========================================================================
    # Session Management
    # ========================================================================

    @app.get("/api/sessions")
    async def get_sessions():
        """List all sessions."""
        sessions = state.sessions.list_sessions()
        # Add message_count to each session
        result = []
        for s in sessions:
            session_data = dict(s)
            key = s.get("key", "")

            # Filter: only show web sessions (channel must be "web")
            if not key or not key.startswith("web:"):
                continue

            if key:
                # Use get_session_messages() to read from disk directly
                messages = state.sessions.get_session_messages(key)
                session_data["message_count"] = len(messages)
            result.append(session_data)
        return {"sessions": result}

    @app.get("/api/sessions/{session_key}")
    async def get_session(session_key: str):
        """Get session details and message history."""
        messages = state.sessions.get_session_messages(session_key)
        return {
            "session_key": session_key,
            "messages": messages
        }

    @app.delete("/api/sessions/{session_key}")
    async def delete_session(session_key: str):
        """Delete a session."""
        success = state.sessions.delete_session(session_key)
        return {"status": "ok", "deleted": session_key, "success": success}

    @app.post("/api/sessions")
    async def create_session(request: Request):
        """Create a new session."""
        body = await request.json()
        key = body.get("key")
        title = body.get("title")

        if not key:
            # Generate a unique key
            import uuid
            key = f"web:{uuid.uuid4().hex[:8]}"

        session = state.sessions.create_session(key, title)
        return {"status": "ok", "session": {"key": session.key, "title": title}}

    # ========================================================================
    # Chat (SSE Streaming)
    # ========================================================================

    class ChatRequest(BaseModel):
        message: str
        session_key: str = "web:default"
        channel: str = "web"
        chat_id: str = "default"

    @app.post("/api/chat")
    async def chat(request: ChatRequest):
        """Send a message and get streaming response."""

        # 调试：打印接收到的 session_key
        print(f"[DEBUG] /api/chat: session_key={request.session_key}")

        if state.agent is None:
            # Create agent on the fly for single message
            from nanobot.agent.loop import AgentLoop
            from nanobot.providers.litellm_provider import LiteLLMProvider
            from nanobot.providers.registry import find_by_name

            config = state.config
            model = config.agents.defaults.model
            provider_name = config.get_provider_name(model)
            spec = find_by_name(provider_name)
            p = config.get_provider(model)

            provider = LiteLLMProvider(
                api_key=p.api_key if p else None,
                api_base=config.get_api_base(model),
                default_model=model,
                provider_name=provider_name,
            )

            state.agent = AgentLoop(
                bus=state.bus,
                provider=provider,
                workspace=config.workspace_path,
                model=model,
                max_iterations=config.agents.defaults.max_tool_iterations,
                context_window_tokens=config.agents.defaults.context_window_tokens,
                web_search_config=config.tools.web.search,
                web_proxy=config.tools.web.proxy or None,
                exec_config=config.tools.exec,
                cron_service=state.cron,
                restrict_to_workspace=config.tools.restrict_to_workspace,
                session_manager=state.sessions,
                mcp_servers=config.tools.mcp_servers,
                channels_config=config.channels,
            )

        agent = state.agent

        # Use a queue to collect progress and final response
        queue = asyncio.Queue()

        async def on_progress(content: str, **kwargs):
            """Callback for progress updates."""
            await queue.put(("progress", content))

        async def process_and_enqueue():
            """Process the message and enqueue the response."""
            try:
                # 从 session_key 提取 chat_id，确保定时任务发送到正确的会话
                chat_id = request.session_key.split(":", 1)[1] if ":" in request.session_key else request.session_key

                response = await agent.process_direct(
                    request.message,
                    session_key=request.session_key,
                    channel="web",
                    chat_id=chat_id,
                    on_progress=on_progress,
                )
                await queue.put(("response", response))
            except Exception as e:
                await queue.put(("error", str(e)))

        async def generate():
            """Generate SSE stream."""
            # Start processing
            task = asyncio.create_task(process_and_enqueue())

            try:
                # Stream results
                while True:
                    try:
                        msg_type, content = await asyncio.wait_for(queue.get(), timeout=0.5)
                        yield {
                            "data": json.dumps({
                                "type": msg_type,
                                "content": content
                            })
                        }
                        if msg_type in ("response", "error"):
                            break
                    except asyncio.TimeoutError:
                        # Check if task is done
                        if task.done():
                            break
                        continue
            finally:
                await task

        return EventSourceResponse(generate())

    # ========================================================================
    # Cron Jobs
    # ========================================================================

    @app.get("/api/cron/jobs")
    async def get_cron_jobs():
        """List all cron jobs."""
        if not state.cron:
            return {"jobs": []}

        jobs = state.cron.list_jobs()
        # Convert CronJob objects to dicts for JSON response
        result = []
        for job in jobs:
            result.append({
                "id": job.id,
                "name": job.name,
                "enabled": job.enabled,
                "schedule_kind": job.schedule.kind,
                "cron_expr": job.schedule.expr,
                "interval_s": (job.schedule.every_ms // 1000) if job.schedule.every_ms else None,
                "message": job.payload.message if job.payload else None,
                "next_run_at_ms": job.state.next_run_at_ms,
                "last_run_at_ms": job.state.last_run_at_ms,
            })
        return {"jobs": result}

    @app.post("/api/cron/jobs")
    async def create_cron_job(request: Request):
        """Create a new cron job."""
        body = await request.json()

        from nanobot.cron.types import CronSchedule

        name = body.get("name", "Unnamed")
        message = body.get("message", "")
        cron_expr = body.get("cron_expr")
        interval_s = body.get("interval_s")
        to = body.get("to")  # 目标会话 chat_id

        # Build schedule
        if cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr)
        elif interval_s and interval_s > 0:
            schedule = CronSchedule(kind="every", every_ms=int(interval_s) * 1000)
        else:
            return {"status": "error", "message": "Either cron_expr or interval_s is required"}

        job = state.cron.add_job(
            name=name,
            schedule=schedule,
            message=message,
            deliver=True,
            channel="web",
            to=to,  # 指定目标会话
        )

        return {"status": "ok", "job_id": job.id}

    @app.delete("/api/cron/jobs/{job_id}")
    async def delete_cron_job(job_id: str):
        """Delete a cron job."""
        state.cron.remove_job(job_id)
        return {"status": "ok", "deleted": job_id}

    @app.post("/api/cron/jobs/{job_id}/run")
    async def run_cron_job(job_id: str):
        """Manually trigger a cron job."""
        # Get job and trigger callback
        jobs = state.cron.list_jobs()
        job = next((j for j in jobs if j["id"] == job_id), None)

        if not job:
            return {"status": "error", "message": "Job not found"}

        if state.cron.on_job:
            await state.cron.on_job(job)

        return {"status": "ok", "executed": job_id}

    # ========================================================================
    # Heartbeat
    # ========================================================================

    @app.get("/api/heartbeat")
    async def get_heartbeat_status():
        """Get heartbeat status."""
        config = state.config
        return {
            "enabled": config.gateway.heartbeat.enabled,
            "interval_s": config.gateway.heartbeat.interval_s,
            "last_run": None  # Would need to track in service
        }

    @app.post("/api/heartbeat/trigger")
    async def trigger_heartbeat():
        """Manually trigger heartbeat."""
        # Heartbeat execution requires agent integration
        return {"status": "ok", "message": "Heartbeat triggered"}

    # ========================================================================
    # WebSocket for real-time chat
    # ========================================================================

    @app.websocket("/ws/chat/{session_key}")
    async def websocket_chat(websocket: WebSocket, session_key: str):
        """WebSocket endpoint for real-time chat."""
        await websocket.accept()

        try:
            while True:
                data = await websocket.receive_text()

                if state.agent is None:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Agent not initialized"
                    })
                    continue

                try:
                    # Send progress updates
                    async def on_progress(content: str):
                        await websocket.send_json({
                            "type": "progress",
                            "content": content
                        })

                    response = await state.agent.process_direct(
                        data,
                        session_key=session_key,
                        channel="web",
                        chat_id="websocket",
                        on_progress=on_progress,
                    )

                    await websocket.send_json({
                        "type": "response",
                        "content": response
                    })

                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "content": str(e)
                    })

        except WebSocketDisconnect:
            pass

    # ========================================================================
    # WebSocket for system events
    # ========================================================================

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        """WebSocket endpoint for system events."""
        await websocket.accept()

        try:
            # Send initial status
            await websocket.send_json({
                "type": "status",
                "data": {
                    "connected": True,
                    "timestamp": asyncio.get_event_loop().time()
                }
            })

            # Keep connection alive
            while True:
                await asyncio.sleep(30)
                await websocket.send_json({
                    "type": "ping"
                })

        except WebSocketDisconnect:
            pass

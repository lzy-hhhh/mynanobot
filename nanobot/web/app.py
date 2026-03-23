"""nanobot Web API - FastAPI application."""

import json
import asyncio
import logging
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

logger = logging.getLogger(__name__)


async def broadcast_new_message(websocket_connections: dict, session_key: str, message: dict):
    """Broadcast a new message to all connected WebSocket clients for a session."""
    if websocket_connections is None:
        logger.warning("WebSocket connections not initialized")
        return

    # Send to global pool (all clients)
    if "global" not in websocket_connections:
        logger.warning("No WebSocket clients connected")
        return

    disconnected = []
    for ws in websocket_connections["global"]:
        try:
            await ws.send_json({
                "type": "new_message",
                "data": {
                    "session_key": session_key,
                    "message": message
                }
            })
            logger.debug("Broadcasted message to WebSocket client for session: {}", session_key)
        except Exception as e:
            logger.debug("Failed to send to WebSocket client: {}", e)
            disconnected.append(ws)

    # Clean up disconnected clients
    for ws in disconnected:
        try:
            websocket_connections["global"].remove(ws)
        except ValueError:
            pass


class AppState:
    """Application state holder."""
    config: Any = None
    bus: MessageBus = None
    sessions: SessionManager = None
    cron: CronService = None
    heartbeat: HeartbeatService = None
    agent: Any = None
    channels: Any = None
    channel_manager: Any = None
    # WebSocket connections for real-time events
    websocket_connections: dict[str, list[WebSocket]] = None


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
        import sys
        import time

        # Configure loguru to only show INFO and above (filter out DEBUG)
        from loguru import logger
        logger.remove()  # Remove default handler
        logger.add(sys.stderr, level="INFO")

        state.config = load_config()
        state.bus = MessageBus()
        state.sessions = SessionManager(state.config.workspace_path)

        # Create cron service
        cron_store_path = get_cron_dir() / "jobs.json"
        state.cron = CronService(cron_store_path)

        # Create agent
        from nanobot.agent.loop import AgentLoop
        from nanobot.providers.litellm_provider import LiteLLMProvider
        from nanobot.providers.registry import find_by_name
        from nanobot.channels.manager import ChannelManager

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

        # Create channel manager to handle outbound messages
        state.channel_manager = ChannelManager(config, state.bus)

        # Set cron on_job callback - handle cron job execution through the agent
        async def on_cron_job(job):
            """Handle cron job execution - let the agent process the task."""
            if job.payload and job.payload.message:
                # Same as CLI: pass the instruction directly to agent
                reminder_note = (
                    "[Scheduled Task] Timer finished.\n\n"
                    f"Task '{job.name}' has been triggered.\n"
                    f"Scheduled instruction: {job.payload.message}"
                )

                # Use same channel and chat_id as job payload (same as CLI)
                target_channel = job.payload.channel or "web"
                target_chat_id = job.payload.to or "default"

                session_key = f"cron:{job.id}"

                response = await state.agent.process_direct(
                    content=reminder_note,
                    session_key=session_key,
                    channel=target_channel,
                    chat_id=target_chat_id,
                )

                logger.info("Cron job '{}' executed through agent for channel '{}'",
                           job.name, target_channel)
                return response
            return None

        state.cron.on_job = on_cron_job
        await state.cron.start()

        # Start channel manager dispatcher in background
        if state.channel_manager.enabled_channels:
            asyncio.create_task(state.channel_manager._dispatch_outbound())
            logger.info("Channel dispatcher started with channels: {}", state.channel_manager.enabled_channels)

        # Set WebSocket broadcast hook for WebChannel
        from nanobot.channels.web import set_websocket_broadcast_hook

        # Create a wrapper function that captures state.websocket_connections
        async def broadcast_hook(session_key: str, message: dict):
            logger.info("Broadcast hook called for session: {}", session_key)
            await broadcast_new_message(state.websocket_connections, session_key, message)

        set_websocket_broadcast_hook(broadcast_hook)
        logger.info("WebSocket broadcast hook registered")

        # Record startup time
        app.state.startup_time = time.time()

        print("[web] FastAPI server started")

    @app.on_event("shutdown")
    async def shutdown():
        """Cleanup on shutdown."""
        if hasattr(state, 'channel_manager') and state.channel_manager:
            await state.channel_manager.stop_all()
        if hasattr(state, 'cron') and state.cron:
            state.cron.stop()

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
        from nanobot.channels.registry import discover_all
        import time
        import json
        import psutil
        import os

        config = state.config
        providers_status = {}

        # 读取原始配置数据
        config_path = get_config_path()
        raw_providers = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                raw_providers = raw_data.get("providers", {})

        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            raw_config = raw_providers.get(spec.name, {})
            if p is None and not raw_config:
                continue

            if spec.is_oauth:
                # OAuth providers: only show configured if access_token exists
                providers_status[spec.name] = {
                    "status": "oauth",
                    "configured": bool(getattr(p, "access_token", None) if p else False)
                }
            elif spec.is_local:
                api_base = p.api_base if p and hasattr(p, "api_base") else raw_config.get("api_base", "")
                providers_status[spec.name] = {
                    "status": "local",
                    "configured": bool(api_base),
                    "api_base": api_base
                }
            else:
                api_key = p.api_key if p and hasattr(p, "api_key") else raw_config.get("api_key", "")
                api_base = p.api_base if p and hasattr(p, "api_base") else raw_config.get("api_base", "")
                providers_status[spec.name] = {
                    "status": "api_key",
                    "configured": bool(api_key),
                    "api_key_preview": api_key[:4] + "..." if api_key and len(api_key) > 4 else (api_key or ""),
                    "api_base": api_base
                }

        # 使用 config dict 来获取 channels 状态
        channels_status = {}
        config_path = get_config_path()
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            channels_data = config_data.get("channels", {})
            for name, cfg in channels_data.items():
                if isinstance(cfg, dict):
                    channels_status[name] = {"enabled": cfg.get("enabled", False)}
                elif hasattr(cfg, "enabled"):
                    channels_status[name] = {"enabled": cfg.enabled}

        # 添加渠道运行状态（如果 channel manager 已初始化）
        if hasattr(state, 'channel_manager') and state.channel_manager:
            for name, channel in state.channel_manager.channels.items():
                if name in channels_status:
                    channels_status[name]["running"] = getattr(channel, "_running", False)
        elif hasattr(state, 'channels') and state.channels:
            for name, channel in state.channels.channels.items():
                if name in channels_status:
                    channels_status[name]["running"] = getattr(channel, "_running", False)

        # 添加所有可用渠道的信息
        all_channels = discover_all()
        for name, cls in all_channels.items():
            if name not in channels_status:
                channels_status[name] = {
                    "enabled": False,
                    "running": False,
                    "display_name": cls.display_name
                }

        cron_status = state.cron.status() if state.cron else {"jobs": 0}

        # 计算运行时间
        uptime_seconds = time.time() - app.state.startup_time if hasattr(app.state, "startup_time") else 0

        # 获取系统资源使用情况
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)  # MB
            cpu_percent = process.cpu_percent()
        except Exception:
            memory_mb = 0
            cpu_percent = 0

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
            },
            "uptime_seconds": int(uptime_seconds),
            "agent_initialized": state.agent is not None,
            "system": {
                "memory_mb": round(memory_mb, 2),
                "cpu_percent": cpu_percent,
                "pid": os.getpid()
            }
        }

    # ========================================================================
    # Config Management
    # ========================================================================

    @app.get("/api/config")
    async def get_config():
        """Get current configuration."""
        import json

        config = state.config

        # 读取原始配置数据
        config_path = get_config_path()
        raw_providers = {}
        raw_channels = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                raw_providers = raw_data.get("providers", {})
                raw_channels = raw_data.get("channels", {})

        return {
            "agents": {
                "defaults": {
                    "model": config.agents.defaults.model,
                    "provider": config.agents.defaults.provider,
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
            "providers": raw_providers,
            "channels": raw_channels,
        }

    @app.post("/api/config")
    async def update_config(request: Request):
        """Update configuration."""
        from nanobot.config.loader import save_config, load_config

        body = await request.json()
        config = state.config

        # 递归更新配置对象
        def update_nested(current, updates):
            for key, value in updates.items():
                if hasattr(current, key):
                    if isinstance(value, dict) and hasattr(getattr(current, key, None), "__dict__"):
                        update_nested(getattr(current, key), value)
                    else:
                        setattr(current, key, value)

        # 更新各部分配置
        if "agents" in body:
            update_nested(config.agents, body["agents"])
        if "gateway" in body:
            update_nested(config.gateway, body["gateway"])
        if "providers" in body:
            for provider_name, provider_config in body["providers"].items():
                if hasattr(config.providers, provider_name):
                    update_nested(getattr(config.providers, provider_name), provider_config)
        if "tools" in body:
            update_nested(config.tools, body["tools"])

        # 保存到文件
        save_config(config)

        # 重新加载配置以确保生效
        state.config = load_config()

        return {"status": "ok"}

    # ========================================================================
    # Channel Management
    # ========================================================================

    @app.get("/api/channels")
    async def get_channels():
        """Get all channels status."""
        from nanobot.channels.registry import discover_all
        import json

        config = state.config
        all_channels = discover_all()
        result = []

        # 读取原始配置数据以获取完整配置
        config_path = get_config_path()
        raw_channels = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                raw_channels = raw_data.get("channels", {})

        for name, cls in sorted(all_channels.items()):
            # Web 渠道不需要开关（始终可用）
            if name == "web":
                continue

            section = getattr(config.channels, name, None)
            raw_config = raw_channels.get(name, {})

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
                "configured": bool(raw_config and any(v for v in raw_config.values() if v not in [None, "", []])),
                "config": raw_config  # 返回完整配置用于编辑
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

    @app.put("/api/channels/{channel_name}/config")
    async def update_channel_config(channel_name: str, request: Request):
        """Update channel detailed configuration."""
        from nanobot.config.loader import save_config, load_config

        body = await request.json()
        config = state.config

        # 检查渠道是否存在于配置中
        if not hasattr(config.channels, channel_name):
            # 尝试从原始配置数据中创建
            config_path = get_config_path()
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "channels" not in data:
                data["channels"] = {}
            data["channels"][channel_name] = body

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            state.config = load_config()
            return {"status": "ok", "channel": channel_name}

        # 更新现有渠道配置
        channel_config = getattr(config.channels, channel_name)

        for key, value in body.items():
            if isinstance(channel_config, dict):
                channel_config[key] = value
            elif hasattr(channel_config, key):
                setattr(channel_config, key, value)

        # 保存到文件
        save_config(config)

        # 重新加载配置
        state.config = load_config()

        return {"status": "ok", "channel": channel_name}

    # ========================================================================
    # Session Management
    # ========================================================================

    @app.get("/api/sessions")
    async def get_sessions():
        """List all sessions."""
        import os

        sessions = state.sessions.list_sessions()
        # Add message_count and title to each session
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

                # Read title from meta.json if exists
                session_dir = state.sessions.workspace / key.replace(":", "_")
                meta_file = session_dir / "meta.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            session_data["title"] = meta.get("title", "")
                    except Exception:
                        pass
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
        return {"status": "ok", "session": {"key": session.key, "title": title or key.split(":")[-1]}}

    @app.put("/api/sessions/{session_key}/title")
    async def update_session_title(session_key: str, request: Request):
        """Update session title/name."""
        body = await request.json()
        title = body.get("title", "")

        # Store title in session metadata
        session_dir = state.sessions.workspace / session_key.replace(":", "_")
        session_dir.mkdir(parents=True, exist_ok=True)

        meta_file = session_dir / "meta.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
        else:
            meta = {"key": session_key}

        meta["title"] = title
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        return {"status": "ok", "title": title}

    # ========================================================================
    # Session Groups
    # ========================================================================

    def _get_groups_file() -> Path:
        """Get the session groups file path."""
        groups_file = state.sessions.workspace / "sessions" / "groups.json"
        groups_file.parent.mkdir(parents=True, exist_ok=True)
        return groups_file

    def _load_groups() -> list[dict]:
        """Load session groups from file."""
        groups_file = _get_groups_file()
        if not groups_file.exists():
            return []
        try:
            with open(groups_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_groups(groups: list[dict]) -> None:
        """Save session groups to file."""
        groups_file = _get_groups_file()
        with open(groups_file, "w", encoding="utf-8") as f:
            json.dump(groups, f, indent=2, ensure_ascii=False)

    @app.get("/api/session-groups")
    async def get_session_groups():
        """Get all session groups."""
        groups = _load_groups()
        return {"groups": groups}

    @app.post("/api/session-groups")
    async def create_session_group(request: Request):
        """Create a new session group."""
        body = await request.json()
        name = body.get("name", "未命名分组")
        icon = body.get("icon", "📁")

        groups = _load_groups()
        # Generate new group ID
        group_id = f"group_{len(groups) + 1}"

        new_group = {
            "id": group_id,
            "name": name,
            "icon": icon,
            "sessions": []
        }
        groups.append(new_group)
        _save_groups(groups)

        return {"status": "ok", "group": new_group}

    @app.put("/api/session-groups/{group_id}")
    async def update_session_group(group_id: str, request: Request):
        """Update a session group."""
        body = await request.json()
        groups = _load_groups()

        for group in groups:
            if group["id"] == group_id:
                if "name" in body:
                    group["name"] = body["name"]
                if "icon" in body:
                    group["icon"] = body["icon"]
                if "sessions" in body:
                    group["sessions"] = body["sessions"]
                _save_groups(groups)
                return {"status": "ok", "group": group}

        return {"status": "error", "message": "Group not found"}

    @app.delete("/api/session-groups/{group_id}")
    async def delete_session_group(group_id: str):
        """Delete a session group."""
        groups = _load_groups()
        groups = [g for g in groups if g["id"] != group_id]
        _save_groups(groups)
        return {"status": "ok"}

    @app.post("/api/session-groups/{group_id}/sessions")
    async def add_session_to_group(group_id: str, request: Request):
        """Add a session to a group."""
        body = await request.json()
        session_key = body.get("session_key")

        if not session_key:
            return {"status": "error", "message": "session_key is required"}

        groups = _load_groups()
        for group in groups:
            if group["id"] == group_id:
                if session_key not in group["sessions"]:
                    group["sessions"].append(session_key)
                _save_groups(groups)
                return {"status": "ok", "group": group}

        return {"status": "error", "message": "Group not found"}

    @app.delete("/api/session-groups/{group_id}/sessions/{session_key}")
    async def remove_session_from_group(group_id: str, session_key: str):
        """Remove a session from a group."""
        groups = _load_groups()
        for group in groups:
            if group["id"] == group_id:
                if session_key in group["sessions"]:
                    group["sessions"].remove(session_key)
                _save_groups(groups)
                return {"status": "ok", "group": group}

        return {"status": "error", "message": "Group not found"}

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
        channel = body.get("channel", "web")  # 支持指定渠道：web, email, feishu 等
        to = body.get("to")  # 目标会话 chat_id 或邮箱地址

        # Build schedule
        if cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr)
        elif interval_s and interval_s > 0:
            schedule = CronSchedule(kind="every", every_ms=int(interval_s) * 1000)
        else:
            return {"status": "error", "message": "Either cron_expr or interval_s is required"}

        # For email channel, extract email from message if to is not provided
        if channel == "email" and not to:
            import re
            email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', message)
            if email_match:
                to = email_match.group(1)

        job = state.cron.add_job(
            name=name,
            schedule=schedule,
            message=message,
            deliver=True,
            channel=channel,  # 支持任意已配置的渠道
            to=to,  # 指定目标会话或邮箱地址
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
        job = next((j for j in jobs if j.id == job_id), None)

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

        # Initialize websocket connections dict if not exists
        if state.websocket_connections is None:
            state.websocket_connections = {}
            logger.info("Initialized WebSocket connections dict")

        # Add connection to the default pool (for global events)
        if "global" not in state.websocket_connections:
            state.websocket_connections["global"] = []
        state.websocket_connections["global"].append(websocket)

        logger.info("WebSocket client connected. Total connections: {}", len(state.websocket_connections["global"]))

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
                try:
                    await websocket.send_json({
                        "type": "ping"
                    })
                except Exception:
                    break

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        finally:
            # Remove connection on disconnect
            if "global" in state.websocket_connections:
                try:
                    state.websocket_connections["global"].remove(websocket)
                    logger.info("WebSocket client removed. Remaining connections: {}", len(state.websocket_connections["global"]))
                except ValueError:
                    pass

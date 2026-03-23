"""Web channel for nanobot web UI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel


# Global hook for broadcasting messages via WebSocket (set by web app)
_broadcast_hook: Callable[[str, dict], Awaitable[None]] | None = None


def set_websocket_broadcast_hook(hook: Callable[[str, dict], Awaitable[None]] | None) -> None:
    """Set or clear the WebSocket broadcast hook."""
    global _broadcast_hook
    _broadcast_hook = hook


class WebChannel(BaseChannel):
    """
    Web channel for nanobot web UI.

    This channel handles outbound messages for the web interface.
    Messages are saved to session JSONL files.
    """

    name: str = "web"
    display_name: str = "Web UI"

    def __init__(self, config: Any, bus: MessageBus):
        super().__init__(config, bus)
        # Get workspace from config or use default
        workspace = Path.home() / ".nanobot" / "workspace"
        if hasattr(config, "workspace_path"):
            workspace = Path(config.workspace_path)
        elif hasattr(config, "workspace"):
            workspace = Path(config.workspace)
        self.sessions_dir = workspace / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """Start the web channel."""
        self._running = True
        logger.info("Web channel started")

    async def stop(self) -> None:
        """Stop the web channel."""
        self._running = False
        logger.info("Web channel stopped")

    def _get_session_path(self, chat_id: str) -> Path:
        """Get the session file path for a chat_id."""
        # Use consistent naming with SessionManager: web:{chat_id} -> web_{chat_id}.jsonl
        safe_id = chat_id.replace(":", "_").replace("/", "_").replace("\\", "_")
        return self.sessions_dir / f"web_{safe_id}.jsonl"

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through the web channel.

        Note: Messages are already saved by AgentLoop._process_message() to session files.
        This method just logs the message for debugging purposes and broadcasts via WebSocket.
        Progress messages (_progress, _tool_hint) are not persisted or broadcast.
        """
        chat_id = msg.chat_id

        # Skip progress messages - they are for real-time display only
        if msg.metadata.get("_progress") or msg.metadata.get("_tool_hint"):
            logger.debug("Skipping progress message for session: web:{}", chat_id)
            return

        # Broadcast message via WebSocket if hook is set
        if _broadcast_hook is not None:
            session_key = f"web:{chat_id}"
            message_data = {
                "role": "assistant",
                "content": msg.content,
                "reasoning_content": getattr(msg, "reasoning_content", None),
                "timestamp": datetime.now().isoformat(),  # Use current time since OutboundMessage doesn't have timestamp
                "metadata": msg.metadata or {}
            }
            try:
                logger.info("Broadcasting message to WebSocket session: {}", session_key)
                await _broadcast_hook(session_key, message_data)
                logger.info("Message broadcast successfully to session: {}", session_key)
            except Exception as e:
                logger.error("Failed to broadcast message to session {}: {}", session_key, e)
        else:
            logger.warning("WebSocket broadcast hook is not set - messages won't be pushed in real-time")

        # Don't save message here - Agent already saved it to session file
        # This prevents duplicate messages
        logger.debug("Web message routed to session: web:{}", chat_id)

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        """Return default config for web channel."""
        return {"enabled": True}

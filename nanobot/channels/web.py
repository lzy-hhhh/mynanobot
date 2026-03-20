"""Web channel for nanobot web UI."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel


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
        if hasattr(config, "workspace"):
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
        safe_id = chat_id.replace(":", "_").replace("/", "_").replace("\\", "_")
        return self.sessions_dir / f"web_{safe_id}.jsonl"

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through the web channel.

        Messages are saved to session JSONL files.
        """
        chat_id = msg.chat_id
        path = self._get_session_path(chat_id)

        # Build message entry
        message_entry = {
            "role": "assistant",
            "content": msg.content,
            "timestamp": datetime.now().isoformat(),
            "metadata": msg.metadata or {}
        }

        # Load existing metadata and messages
        metadata = {
            "key": f"web:{chat_id}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": {},
            "last_consolidated": 0
        }
        existing_messages = []

        if path.exists():
            # Read existing metadata and messages
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    try:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            metadata = data
                            metadata["updated_at"] = datetime.now().isoformat()
                    except Exception:
                        pass
                # Read remaining lines as messages
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("_type") != "metadata":
                                existing_messages.append(data)
                        except Exception:
                            pass

        # Write session file
        with open(path, "w", encoding="utf-8") as f:
            # Write metadata
            metadata_line = {"_type": "metadata", **metadata}
            f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")

            # Write existing messages
            for msg_data in existing_messages:
                f.write(json.dumps(msg_data, ensure_ascii=False) + "\n")

            # Write new message
            f.write(json.dumps(message_entry, ensure_ascii=False) + "\n")

        logger.debug("Web message saved to session: web:{}", chat_id)

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        """Return default config for web channel."""
        return {"enabled": True}

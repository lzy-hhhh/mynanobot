"""Event types for the message bus."""

from dataclasses import dataclass, field#数据类，自动生成初始化方法和其他特殊方法，简化类的定义。这里定义了两个数据类：InboundMessage和OutboundMessage，分别表示从聊天渠道接收的消息和要发送到聊天渠道的消息。这些类包含了消息的基本属性，如频道、发送者ID、聊天ID、内容、时间戳、媒体列表和元数据等，以及一个用于唯一标识会话的session_key属性。
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """Message received from a chat channel."""

    channel: str  # telegram, discord, slack, whatsapp
    sender_id: str  # User identifier
    chat_id: str  # Chat/channel identifier
    content: str  # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data
    session_key_override: str | None = None  # Optional override for thread-scoped sessions

    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""

    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)



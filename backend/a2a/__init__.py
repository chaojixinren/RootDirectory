"""A2A通信模块 — Agent间消息传递."""

from .bus import MessageBus
from .message import MessageType, MessageBuilder
from backend.models.agent import AgentMessage as Message

__all__ = [
    "MessageBus",
    "Message",
    "MessageType",
    "MessageBuilder",
]

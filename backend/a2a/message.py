"""消息类型定义 — 扩展models.py中的AgentMessage."""

from __future__ import annotations

from enum import Enum
from typing import Any

from backend.models.agent import AgentMessage


class MessageType(str, Enum):
    """标准消息类型."""

    # 任务相关
    TASK_ASSIGN = "task_assign"  # 任务分配
    TASK_RESULT = "task_result"  # 任务结果
    TASK_QUERY = "task_query"  # 任务查询

    # 协调相关
    COORDINATE = "coordinate"  # 协调请求
    COORDINATE_ACK = "coordinate_ack"  # 协调确认

    # 反思相关
    REFLECTION = "reflection"  # 反思结果
    REFLECTION_REQUEST = "reflection_request"  # 请求反思

    # 记忆相关
    MEMORY_UPDATE = "memory_update"  # 记忆更新
    MEMORY_QUERY = "memory_query"  # 记忆查询

    # 子Agent相关
    SPAWN_REQUEST = "spawn_request"  # 派生子Agent请求
    SPAWN_RESULT = "spawn_result"  # 子Agent结果
    SPAWN_COMPLETE = "spawn_complete"  # 子Agent完成

    # 状态相关
    STATUS_UPDATE = "status_update"  # 状态更新
    HEARTBEAT = "heartbeat"  # 心跳

    # 错误相关
    ERROR = "error"  # 错误通知
    RETRY = "retry"  # 重试请求


class MessageBuilder:
    """消息构建器.
    
    简化消息创建过程。
    """

    @staticmethod
    def task_assign(
        from_agent: str,
        to_agent: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """构建任务分配消息."""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.TASK_ASSIGN,
            payload={
                "task": task,
                "context": context or {},
            },
            natural_language=f"分配任务: {task[:50]}...",
        )

    @staticmethod
    def task_result(
        from_agent: str,
        to_agent: str,
        result: dict[str, Any],
        status: str = "success",
    ) -> AgentMessage:
        """构建任务结果消息."""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.TASK_RESULT,
            payload={
                "status": status,
                "result": result,
            },
            natural_language=f"任务完成，状态: {status}",
        )

    @staticmethod
    def reflection_request(
        from_agent: str,
        to_agent: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """构建反思请求消息."""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.REFLECTION_REQUEST,
            payload={
                "reason": reason,
                "context": context or {},
            },
            natural_language=f"请求反思: {reason}",
        )

    @staticmethod
    def spawn_request(
        from_agent: str,
        to_agent: str,
        parent_task_id: str,
        sub_tasks: list[dict[str, Any]],
    ) -> AgentMessage:
        """构建子Agent派生请求."""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.SPAWN_REQUEST,
            payload={
                "parent_task_id": parent_task_id,
                "sub_tasks": sub_tasks,
            },
            natural_language=f"请求派生 {len(sub_tasks)} 个子Agent",
        )

    @staticmethod
    def status_update(
        from_agent: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """构建状态更新消息（广播）."""
        return AgentMessage(
            from_agent=from_agent,
            to_agent="*",  # 广播
            msg_type=MessageType.STATUS_UPDATE,
            payload={
                "status": status,
                "details": details or {},
            },
            natural_language=f"状态更新: {status}",
        )

    @staticmethod
    def error(
        from_agent: str,
        to_agent: str,
        error: str,
        recoverable: bool = True,
    ) -> AgentMessage:
        """构建错误消息."""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.ERROR,
            payload={
                "error": error,
                "recoverable": recoverable,
            },
            natural_language=f"错误: {error[:100]}...",
        )

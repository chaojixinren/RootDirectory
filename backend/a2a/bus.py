"""消息总线 — Agent间消息传递."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from backend.models.agent import AgentMessage


class MessageBus:
    """消息总线.
    
    管理Agent间的消息传递，支持发布-订阅模式。
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[AgentMessage], Any]]] = {}
        self._history: list[AgentMessage] = []
        self._max_history = 1000
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        agent_id: str,
        handler: Callable[[AgentMessage], Any],
    ) -> None:
        """订阅消息.
        
        Args:
            agent_id: Agent ID
            handler: 消息处理函数
        """
        async with self._lock:
            if agent_id not in self._subscribers:
                self._subscribers[agent_id] = []
            self._subscribers[agent_id].append(handler)

    async def unsubscribe(
        self,
        agent_id: str,
        handler: Callable[[AgentMessage], Any] | None = None,
    ) -> None:
        """取消订阅.
        
        Args:
            agent_id: Agent ID
            handler: 指定处理函数，None则取消所有
        """
        async with self._lock:
            if agent_id in self._subscribers:
                if handler is None:
                    del self._subscribers[agent_id]
                else:
                    self._subscribers[agent_id] = [
                        h for h in self._subscribers[agent_id] if h != handler
                    ]

    async def publish(self, message: AgentMessage) -> None:
        """发布消息.
        
        Args:
            message: 要发布的消息
        """
        # 保存到历史
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        # 发送给目标Agent
        to_agent = message.to_agent
        
        async with self._lock:
            handlers = self._subscribers.get(to_agent, []).copy()
        
        # 调用处理器
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                print(f"[MessageBus] 消息处理失败: {e}")

    async def broadcast(
        self,
        message: AgentMessage,
        exclude: list[str] | None = None,
    ) -> None:
        """广播消息.
        
        Args:
            message: 要广播的消息
            exclude: 要排除的Agent列表
        """
        exclude_set = set(exclude or [])
        exclude_set.add(message.from_agent)  # 排除发送者
        
        async with self._lock:
            all_agents = list(self._subscribers.keys())
        
        for agent_id in all_agents:
            if agent_id not in exclude_set:
                msg_copy = AgentMessage(
                    from_agent=message.from_agent,
                    to_agent=agent_id,
                    msg_type=message.msg_type,
                    payload=message.payload,
                    natural_language=message.natural_language,
                )
                await self.publish(msg_copy)

    def get_history(
        self,
        agent_id: str | None = None,
        msg_type: str | None = None,
        limit: int = 100,
    ) -> list[AgentMessage]:
        """获取消息历史.
        
        Args:
            agent_id: 过滤特定Agent
            msg_type: 过滤特定消息类型
            limit: 返回数量限制
            
        Returns:
            消息列表
        """
        filtered = self._history
        
        if agent_id:
            filtered = [
                m for m in filtered
                if m.from_agent == agent_id or m.to_agent == agent_id
            ]
        
        if msg_type:
            filtered = [m for m in filtered if m.msg_type == msg_type]
        
        return filtered[-limit:]

    def clear_history(self) -> None:
        """清空历史."""
        self._history.clear()


class MessageBusHandler:
    """消息总线处理器.
    
    实现Agent的MessageHandler协议。
    """

    def __init__(self, bus: MessageBus, agent_id: str):
        self.bus = bus
        self.agent_id = agent_id

    async def send_message(self, message: AgentMessage) -> None:
        """发送消息到总线."""
        await self.bus.publish(message)

    async def receive_message(self, timeout: float | None = None) -> AgentMessage | None:
        """接收消息（阻塞）."""
        future: asyncio.Future[AgentMessage] = asyncio.Future()
        
        def handler(msg: AgentMessage) -> None:
            if not future.done():
                future.set_result(msg)
        
        await self.bus.subscribe(self.agent_id, handler)
        
        try:
            if timeout:
                return await asyncio.wait_for(future, timeout=timeout)
            else:
                return await future
        except asyncio.TimeoutError:
            return None
        finally:
            await self.bus.unsubscribe(self.agent_id, handler)

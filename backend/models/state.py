"""LangGraph状态定义 — 用于工作流图."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from .base import BaseSchema
from .memory import MemoryDigest, Clue
from .agent import RoundRecord, AgentMessage


def merge_lists(left: list[Any], right: list[Any]) -> list[Any]:
    """合并两个列表 — 用于Reducers."""
    return left + right


def merge_or_clear_lists(left: list[Any], right: list[Any] | None) -> list[Any]:
    """合并列表，但当 right 为 None 时清空 — 用于需要重置的列表."""
    if right is None:
        return []
    return left + right


def replace_value(left: Any, right: Any) -> Any:
    """替换值 — 用于Reducers."""
    return right


class AgentState(BaseSchema):
    """单个Agent的内部状态."""

    agent_id: str = Field(description="Agent ID")
    role: str = Field(description="Agent角色")
    current_task: str | None = Field(None, description="当前任务")
    step_count: int = Field(default=0, description="当前步数")
    max_steps: int = Field(default=10, description="最大步数")
    status: str = Field(default="idle", description="状态")
    context: dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    messages: list[AgentMessage] = Field(default_factory=list, description="消息历史")


class GraphState(BaseSchema):
    """LangGraph 全局状态 — 在工作流节点间传递.
    
    使用 Annotated 定义 Reducer 函数，控制状态更新方式.
    """

    # 任务信息
    task_id: str = Field(description="任务ID")
    goal: str = Field(description="任务目标")
    context: str = Field(default="", description="任务上下文")

    # 执行状态
    current_round: int = Field(default=0, description="当前轮次")
    max_rounds: int = Field(default=20, description="最大轮数")
    should_continue: bool = Field(default=True, description="是否继续执行")
    is_completed: bool = Field(default=False, description="是否已完成")
    is_stalled: bool = Field(default=False, description="是否已停滞")

    # Agent状态列表（使用Annotated定义Reducer）
    agent_states: Annotated[list[AgentState], merge_lists] = Field(
        default_factory=list, description="所有Agent状态"
    )

    # 轮次记录
    rounds: Annotated[list[RoundRecord], merge_lists] = Field(
        default_factory=list, description="历史轮次"
    )

    # 记忆
    memory_digest: MemoryDigest | None = Field(None, description="记忆摘要")
    recent_clues: Annotated[list[Clue], merge_lists] = Field(
        default_factory=list, description="近期线索"
    )

    # 当前轮次数据
    current_plan: str = Field(default="", description="当前计划")
    sub_tasks: list[dict[str, Any]] = Field(
        default_factory=list, description="当前子任务（每轮替换）"
    )
    agent_results: Annotated[list[dict[str, Any]], merge_or_clear_lists] = Field(
        default_factory=list, description="Agent执行结果（并行合并，支持清空）"
    )
    reflection_result: str | None = Field(None, description="反思结果")

    # 子Agent派生
    spawn_requests: Annotated[list[dict[str, Any]], merge_lists] = Field(
        default_factory=list, description="子Agent派生请求"
    )

    # 执行追踪事件
    trace_events: Annotated[list[dict[str, Any]], merge_lists] = Field(
        default_factory=list, description="执行追踪事件（包含提示词、响应、上下文等）"
    )

    # 最终结果
    final_result: str | None = Field(None, description="最终结果")
    error: str | None = Field(None, description="错误信息")

    def get_agent_state(self, agent_id: str) -> AgentState | None:
        """获取指定Agent的状态."""
        for state in self.agent_states:
            if state.agent_id == agent_id:
                return state
        return None

    def update_agent_state(self, agent_state: AgentState) -> None:
        """更新Agent状态（替换或添加）."""
        existing = self.get_agent_state(agent_state.agent_id)
        if existing:
            self.agent_states.remove(existing)
        self.agent_states.append(agent_state)

    def add_clue(self, clue: Clue) -> None:
        """添加线索并限制数量."""
        self.recent_clues.append(clue)
        # 只保留最近50条线索
        if len(self.recent_clues) > 50:
            self.recent_clues = self.recent_clues[-50:]

    def to_snapshot(self) -> dict[str, Any]:
        """转换为快照字典（用于调试）."""
        return {
            "task_id": self.task_id,
            "current_round": self.current_round,
            "goal": self.goal[:100] + "..." if len(self.goal) > 100 else self.goal,
            "status": {
                "should_continue": self.should_continue,
                "is_completed": self.is_completed,
                "is_stalled": self.is_stalled,
            },
            "agents": len(self.agent_states),
            "rounds": len(self.rounds),
            "clues": len(self.recent_clues),
        }

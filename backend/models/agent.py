"""Agent相关模型."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .base import BaseSchema, new_id, utc_now


class AgentRole(str, Enum):
    """Agent角色枚举."""

    ORCHESTRATOR = "orchestrator"  # 决策Agent
    THINKER = "thinker"  # 思考专家
    EXECUTOR = "executor"  # 执行专家
    REFLECTOR = "reflector"  # 反思Agent
    MEMORY = "memory"  # 记忆Agent

    # 安全专家团队
    WEB_SECURITY = "web_security"  # Web安全专家
    NETWORK_PENETRATION = "network_penetration"  # 网络渗透专家
    CODE_AUDITOR = "code_auditor"  # 代码审计专家
    MOBILE_SECURITY = "mobile_security"  # 移动安全专家
    SECURITY_OPS = "security_ops"  # 安全运营专家


class AgentStatus(str, Enum):
    """Agent状态."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentConfig(BaseSchema):
    """Agent运行配置，支持自定义prompt."""

    agent_id: str = Field(default_factory=new_id)
    role: AgentRole = Field(description="Agent角色")
    name: str = Field(description="Agent名称")
    model: str = Field(default="gpt-4o", description="使用的LLM模型")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, ge=100, le=16000)
    system_prompt: str = Field(default="", description="系统提示词")
    max_steps: int = Field(default=15, ge=1, le=50, description="最大执行步数")
    tools: list[str] = Field(default_factory=list, description="可用工具列表")
    skills: list[str] = Field(default_factory=list, description="注入的Skills")
    can_spawn_children: bool = Field(default=False, description="是否能派生子Agent")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseSchema):
    """Agent-to-Agent 通信消息，强制 JSON 格式."""

    msg_id: str = Field(default_factory=new_id)
    from_agent: str = Field(description="发送者Agent ID")
    to_agent: str = Field(description="接收者Agent ID")
    msg_type: str = Field(
        description="消息类型: task_assign/result/reflection/memory_update/spawn_request"
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="消息负载")
    timestamp: datetime = Field(default_factory=utc_now)
    # 关键节点 Agent 可附带自然语言说明，便于调试
    natural_language: str | None = Field(None, description="自然语言说明（调试用）")


class AgentResult(BaseSchema):
    """单个 Agent 的执行结果."""

    agent_id: str = Field(description="Agent ID")
    role: AgentRole = Field(description="Agent角色")
    status: str = Field(default="success", description="状态: success/failed/partial")
    summary: str = Field(default="", description="执行摘要")
    output: str = Field(default="", description="原始输出")
    clues: list[dict[str, Any]] = Field(default_factory=list, description="提取的线索")
    tool_calls: list[dict[str, Any]] = Field(default_factory=list, description="工具调用记录")
    execution_time: float = Field(default=0.0, description="执行耗时(秒)")
    timestamp: datetime = Field(default_factory=utc_now)


class RoundRecord(BaseSchema):
    """一轮调度的完整记录."""

    round_index: int = Field(description="轮次索引")
    orchestrator_plan: str = Field(default="", description="决策Agent的计划")
    sub_tasks: list[dict[str, Any]] = Field(default_factory=list, description="子任务")
    agent_results: list[AgentResult] = Field(default_factory=list, description="Agent执行结果")
    reflection_summary: str | None = Field(None, description="反思总结")
    should_continue: bool = Field(default=True, description="是否继续执行")
    timestamp: datetime = Field(default_factory=utc_now)

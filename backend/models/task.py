"""任务相关模型."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .base import BaseSchema, new_id, utc_now


class TaskStatus(str, Enum):
    """任务状态."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"
    CANCELLED = "cancelled"


class SubTaskStatus(str, Enum):
    """子任务状态."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SubTask(BaseSchema):
    """由决策Agent拆分出的子任务单元."""

    id: str = Field(default_factory=new_id)
    description: str = Field(description="任务描述")
    assigned_to: str | None = Field(None, description="分配的Agent ID")
    agent_role: str | None = Field(None, description="分配的角色(thinker/executor)")
    status: SubTaskStatus = Field(default=SubTaskStatus.PENDING)
    max_steps: int = Field(default=10, ge=1, le=50, description="最大执行步数")
    current_step: int = Field(default=0, ge=0, description="当前步数")
    result: str | None = Field(None, description="执行结果")
    error: str | None = Field(None, description="错误信息")
    parent_task_id: str | None = Field(None, description="父任务ID")
    dependencies: list[str] = Field(default_factory=list, description="依赖的子任务ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskRequest(BaseSchema):
    """用户提交的任务请求."""

    goal: str = Field(description="任务目标描述")
    context: str = Field(default="", description="任务上下文/背景信息")
    max_rounds: int = Field(default=20, ge=1, le=100, description="最大执行轮数")
    enable_reflection: bool = Field(default=True, description="是否启用反思Agent")
    required_skills: list[str] = Field(default_factory=list, description="需要的Skills分类")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class TaskResponse(BaseSchema):
    """任务执行响应."""

    task_id: str = Field(description="任务ID")
    status: TaskStatus = Field(description="任务状态")
    result: str | None = Field(None, description="最终结果")
    sub_tasks: list[SubTask] = Field(default_factory=list, description="子任务列表")
    current_round: int = Field(default=0, description="当前执行轮数")
    total_steps: int = Field(default=0, description="总执行步数")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    error: str | None = Field(None, description="错误信息")

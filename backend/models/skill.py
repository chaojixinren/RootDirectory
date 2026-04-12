"""Skills相关模型 — 树状分类."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import BaseSchema, new_id, utc_now


class SkillDefinition(BaseSchema):
    """Skill 元数据定义，含树状分类."""

    name: str = Field(description="Skill名称")
    category: str = Field(description="分类路径，如 'security/pentest/recon'")
    description: str = Field(description="Skill描述")
    when_to_use: str = Field(default="", description="使用场景描述")
    content: str = Field(default="", description="具体指导内容，使用时注入")
    tags: list[str] = Field(default_factory=list, description="标签")
    priority: int = Field(default=0, description="优先级(越高越优先)")
    version: str = Field(default="1.0", description="版本")
    author: str = Field(default="", description="作者")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def category_parts(self) -> list[str]:
        """获取分类路径的各个部分."""
        return self.category.split("/")

    @property
    def full_name(self) -> str:
        """获取完整名称(含分类)."""
        return f"{self.category}/{self.name}"


class SkillNode(BaseSchema):
    """Skill树节点 — 用于前端展示和分类管理."""

    id: str = Field(default_factory=new_id)
    name: str = Field(description="节点名称")
    path: str = Field(description="完整路径")
    is_category: bool = Field(default=False, description="是否为分类节点")
    children: list[SkillNode] = Field(default_factory=list, description="子节点")
    skill: SkillDefinition | None = Field(None, description="如果是Skill，存储定义")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillMatch(BaseSchema):
    """Skill匹配结果."""

    skill: SkillDefinition = Field(description="匹配的Skill")
    score: float = Field(description="匹配分数")
    reason: str = Field(default="", description="匹配原因")


class SkillInjection(BaseSchema):
    """Skill注入记录."""

    task_id: str = Field(description="任务ID")
    agent_id: str = Field(description="Agent ID")
    skills: list[SkillDefinition] = Field(default_factory=list, description="注入的Skills")
    context: str = Field(default="", description="注入上下文")
    timestamp: datetime = Field(default_factory=utc_now)

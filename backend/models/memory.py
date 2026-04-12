"""记忆相关模型 — 参考 memory.py 设计."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import BaseSchema, utc_now


class Clue(BaseSchema):
    """任务过程中发现的关键线索."""

    key: str = Field(description="线索关键词")
    value: str = Field(description="线索值")
    source_agent: str = Field(description="来源Agent")
    round_index: int = Field(default=0, description="所属轮次")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    category: str = Field(default="general", description="线索分类")


class MemoryDigest(BaseSchema):
    """滚动记忆摘要，由 Memory Agent 维护.
    
    参考 memory.py 的设计，将较早轮次的历史压缩成结构化摘要.
    """

    covered_until_round: int = Field(default=0, description="已覆盖的轮次")
    covered_event_count: int = Field(default=0, description="已覆盖的事件数")
    mission_state: str = Field(default="", description="任务进展概括")
    key_decisions: list[str] = Field(default_factory=list, description="关键决策")
    confirmed_findings: list[str] = Field(default_factory=list, description="已确认发现")
    failed_attempts: list[str] = Field(default_factory=list, description="失败尝试")
    open_questions: list[str] = Field(default_factory=list, description="未决问题")
    next_focus: list[str] = Field(default_factory=list, description="后续重点")
    updated_at: datetime = Field(default_factory=utc_now)

    def to_prompt_text(self) -> str:
        """将摘要渲染为可嵌入 prompt 的文本."""
        sections = [
            f"【任务进展】{self.mission_state}" if self.mission_state else "",
            f"【关键决策】{'; '.join(self.key_decisions)}" if self.key_decisions else "",
            f"【已确认发现】{'; '.join(self.confirmed_findings)}" if self.confirmed_findings else "",
            f"【失败尝试】{'; '.join(self.failed_attempts)}" if self.failed_attempts else "",
            f"【未决问题】{'; '.join(self.open_questions)}" if self.open_questions else "",
            f"【后续重点】{'; '.join(self.next_focus)}" if self.next_focus else "",
        ]
        return "\n".join(s for s in sections if s)

    def is_empty(self) -> bool:
        """检查记忆是否为空."""
        return self.covered_until_round == 0 and not self.mission_state


class MemorySnapshot(BaseSchema):
    """记忆快照 — 某一时刻的完整记忆状态."""

    task_id: str = Field(description="任务ID")
    round_index: int = Field(description="轮次")
    digest: MemoryDigest = Field(description="记忆摘要")
    recent_clues: list[Clue] = Field(default_factory=list, description="近期线索")
    recent_rounds: list[dict[str, Any]] = Field(default_factory=list, description="近期轮次(未压缩)")
    timestamp: datetime = Field(default_factory=utc_now)

"""基础模型定义 — 共享的工具函数和基类."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """获取当前UTC时间."""
    return datetime.now(timezone.utc)


def new_id() -> str:
    """生成短ID."""
    return uuid.uuid4().hex[:12]


class StatusEnum(str, Enum):
    """通用状态枚举."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"
    CANCELLED = "cancelled"


class BaseSchema(BaseModel):
    """所有模型的基类."""

    class Config:
        """Pydantic配置."""

        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}

"""工具相关模型."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .base import BaseSchema, new_id, utc_now


class ToolSource(str, Enum):
    """工具来源."""

    BUILTIN = "builtin"  # 内置工具
    MCP = "mcp"  # MCP协议
    CUSTOM = "custom"  # 自定义工具


class ToolDefinition(BaseSchema):
    """工具的元数据定义."""

    name: str = Field(description="工具名称")
    description: str = Field(description="工具描述")
    parameters: dict[str, Any] = Field(default_factory=dict, description="参数Schema")
    source: ToolSource = Field(default=ToolSource.BUILTIN, description="工具来源")
    source_config: dict[str, Any] = Field(default_factory=dict, description="来源配置(MCP等)")
    tags: list[str] = Field(default_factory=list, description="工具标签")
    required_permissions: list[str] = Field(default_factory=list, description="需要的权限")


class ToolExecution(BaseSchema):
    """工具执行记录."""

    execution_id: str = Field(default_factory=new_id)
    tool_name: str = Field(description="工具名称")
    agent_id: str = Field(description="调用者Agent")
    parameters: dict[str, Any] = Field(default_factory=dict, description="调用参数")
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = Field(None)


class ToolResult(BaseSchema):
    """工具执行结果."""

    execution_id: str = Field(default_factory=new_id, description="执行ID")
    success: bool = Field(description="是否成功")
    output: str = Field(default="", description="输出内容")
    error: str | None = Field(None, description="错误信息")
    execution_time: float = Field(default=0.0, description="执行耗时(秒)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    timestamp: datetime = Field(default_factory=utc_now)

    @property
    def is_empty(self) -> bool:
        """检查结果是否为空."""
        return not self.output and not self.error

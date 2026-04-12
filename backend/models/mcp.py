"""MCP协议相关模型."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, HttpUrl

from .base import BaseSchema, new_id, utc_now


class MCPTransport(str, Enum):
    """MCP传输方式."""

    STDIO = "stdio"  # 标准输入输出
    SSE = "sse"  # Server-Sent Events
    HTTP = "http"  # HTTP POST


class MCPConfig(BaseSchema):
    """MCP全局配置."""

    enabled: bool = Field(default=True)
    default_timeout: int = Field(default=30, description="默认超时(秒)")
    max_tools_per_server: int = Field(default=50, description="每个服务器最大工具数")
    auto_register: bool = Field(default=True, description="是否自动注册工具")
    servers: list[MCPServerConfig] = Field(default_factory=list, description="服务器配置列表")


class MCPServerConfig(BaseSchema):
    """单个MCP服务器配置."""

    server_id: str = Field(default_factory=new_id)
    name: str = Field(description="服务器名称")
    transport: MCPTransport = Field(default=MCPTransport.STDIO)
    # STDIO配置
    command: str | None = Field(None, description="命令")
    args: list[str] = Field(default_factory=list, description="参数")
    env: dict[str, str] = Field(default_factory=dict, description="环境变量")
    # HTTP/SSE配置
    url: str | None = Field(None, description="服务器URL")
    headers: dict[str, str] = Field(default_factory=dict, description="请求头")
    # 通用配置
    timeout: int = Field(default=30, description="超时(秒)")
    enabled: bool = Field(default=True)
    auto_reconnect: bool = Field(default=True, description="自动重连")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MCPConnectionState(str, Enum):
    """MCP连接状态."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class MCPConnection(BaseSchema):
    """MCP连接状态记录."""

    server_id: str = Field(description="服务器ID")
    state: MCPConnectionState = Field(default=MCPConnectionState.DISCONNECTED)
    connected_at: datetime | None = Field(None)
    last_error: str | None = Field(None)
    tools_count: int = Field(default=0, description="已注册工具数")
    updated_at: datetime = Field(default_factory=utc_now)

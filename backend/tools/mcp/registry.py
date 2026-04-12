"""MCP工具注册表 — 管理多个MCP服务器的工具."""

from __future__ import annotations

from typing import Any

from backend.models.mcp import MCPConfig, MCPServerConfig
from backend.models.tool import ToolDefinition
from backend.tools.registry import ToolRegistry

from .client import MCPClient


class MCPRegistry:
    """MCP注册表.
    
    管理多个MCP服务器的连接和工具注册。
    """

    def __init__(self, config: MCPConfig | None = None):
        self.config = config or MCPConfig()
        self._clients: dict[str, MCPClient] = {}
        self._tools: dict[str, ToolDefinition] = {}

    async def connect_all(self) -> dict[str, bool]:
        """连接所有配置的服务器.
        
        Returns:
            服务器ID到连接状态的映射
        """
        results = {}
        
        for server_config in self.config.servers:
            if not server_config.enabled:
                continue
            
            client = MCPClient(server_config)
            success = await client.connect()
            
            if success:
                self._clients[server_config.server_id] = client
                # 获取工具列表
                tools = await client.list_tools()
                for tool in tools:
                    self._tools[tool.name] = tool
            
            results[server_config.server_id] = success
        
        return results

    async def disconnect_all(self) -> None:
        """断开所有连接."""
        for client in self._clients.values():
            await client.disconnect()
        
        self._clients.clear()
        self._tools.clear()

    def get_tool(self, name: str) -> ToolDefinition | None:
        """获取工具定义."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """列出所有MCP工具."""
        return list(self._tools.values())

    async def call_tool(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """调用工具."""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"工具不存在: {name}"}
        
        # 找到对应的服务器
        server_id = tool.source_config.get("server_id")
        client = self._clients.get(server_id)
        
        if not client:
            return {"error": f"MCP客户端未连接: {server_id}"}
        
        return await client.call_tool(name, params)

    def register_to_tool_registry(self, registry: ToolRegistry) -> None:
        """将MCP工具注册到主工具注册表."""
        for tool in self._tools.values():
            # 创建异步包装器
            async def handler(params: dict[str, Any], tool_name: str = tool.name) -> Any:
                return await self.call_tool(tool_name, params)
            
            registry.register(tool.name, tool, handler)

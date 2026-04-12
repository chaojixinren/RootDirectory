"""MCP客户端实现 — 标准MCP协议支持."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import httpx
import websockets

from backend.models.mcp import MCPConnectionState, MCPTransport, MCPServerConfig
from backend.models.tool import ToolDefinition, ToolSource


class MCPClient:
    """MCP客户端.
    
    支持多种传输方式：STDIO、SSE、HTTP。
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.state = MCPConnectionState.DISCONNECTED
        self.tools: list[ToolDefinition] = []
        
        # STDIO进程
        self._process: subprocess.Popen | None = None
        
        # WebSocket连接
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def connect(self) -> bool:
        """连接到MCP服务器.
        
        Returns:
            是否连接成功
        """
        if self.config.transport == MCPTransport.STDIO:
            return await self._connect_stdio()
        elif self.config.transport == MCPTransport.SSE:
            return await self._connect_sse()
        elif self.config.transport == MCPTransport.HTTP:
            return await self._connect_http()
        else:
            raise ValueError(f"不支持的传输方式: {self.config.transport}")

    async def _connect_stdio(self) -> bool:
        """通过STDIO连接."""
        try:
            self._process = subprocess.Popen(
                [self.config.command] + self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**dict(subprocess.os.environ), **self.config.env},
            )
            
            # 发送初始化请求
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "nexus", "version": "0.1.0"},
                },
            }
            
            self._send_stdio(init_request)
            response = self._recv_stdio()
            
            if response and "result" in response:
                self.state = MCPConnectionState.CONNECTED
                return True
            
            return False
            
        except Exception as e:
            self.state = MCPConnectionState.ERROR
            return False

    async def _connect_sse(self) -> bool:
        """通过SSE连接."""
        # SSE连接实现（简化版）
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.config.url}/sse",
                    headers=self.config.headers,
                    timeout=self.config.timeout,
                )
                
                if response.status_code == 200:
                    self.state = MCPConnectionState.CONNECTED
                    return True
                
                return False
                
        except Exception:
            self.state = MCPConnectionState.ERROR
            return False

    async def _connect_http(self) -> bool:
        """通过HTTP连接."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.url}/initialize",
                    headers=self.config.headers,
                    json={
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "nexus", "version": "0.1.0"},
                    },
                    timeout=self.config.timeout,
                )
                
                if response.status_code == 200:
                    self.state = MCPConnectionState.CONNECTED
                    return True
                
                return False
                
        except Exception:
            self.state = MCPConnectionState.ERROR
            return False

    def _send_stdio(self, message: dict[str, Any]) -> None:
        """通过STDIO发送消息."""
        if self._process and self._process.stdin:
            data = json.dumps(message) + "\n"
            self._process.stdin.write(data.encode())
            self._process.stdin.flush()

    def _recv_stdio(self) -> dict[str, Any] | None:
        """通过STDIO接收消息."""
        if self._process and self._process.stdout:
            line = self._process.stdout.readline()
            if line:
                return json.loads(line.decode())
        return None

    async def list_tools(self) -> list[ToolDefinition]:
        """获取工具列表."""
        if self.state != MCPConnectionState.CONNECTED:
            return []
        
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        }
        
        if self.config.transport == MCPTransport.STDIO:
            self._send_stdio(request)
            response = self._recv_stdio()
        else:
            # HTTP方式
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.url}/tools/list",
                    headers=self.config.headers,
                    json=request,
                    timeout=self.config.timeout,
                )
                response = response.json()
        
        if response and "result" in response:
            tools_data = response["result"].get("tools", [])
            self.tools = [
                ToolDefinition(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=t.get("parameters", {}),
                    source=ToolSource.MCP,
                    source_config={"server_id": self.config.server_id},
                )
                for t in tools_data
            ]
        
        return self.tools

    async def call_tool(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """调用工具."""
        if self.state != MCPConnectionState.CONNECTED:
            return {"error": "未连接到服务器"}
        
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": params,
            },
        }
        
        if self.config.transport == MCPTransport.STDIO:
            self._send_stdio(request)
            return self._recv_stdio() or {"error": "无响应"}
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.url}/tools/call",
                    headers=self.config.headers,
                    json=request,
                    timeout=self.config.timeout,
                )
                return response.json()

    async def disconnect(self) -> None:
        """断开连接."""
        if self._process:
            self._process.terminate()
            self._process = None
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        self.state = MCPConnectionState.DISCONNECTED

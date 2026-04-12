"""工具执行器 — 执行工具调用."""

from __future__ import annotations

from typing import Any

from .registry import ToolRegistry


class ToolExecutor:
    """工具执行器.

    负责执行工具调用。
    """

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry()

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行工具调用.

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            执行结果
        """
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}

        handler = self.registry.get_handler(tool_name)
        if not handler:
            return {"error": f"Tool '{tool_name}' has no handler"}

        try:
            import inspect
            if inspect.iscoroutinefunction(handler):
                result = await handler(**arguments)
            else:
                result = handler(**arguments)
            # 如果返回的是 ToolResult 对象，转为 dict
            if hasattr(result, 'model_dump'):
                return {"result": result.model_dump()}
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

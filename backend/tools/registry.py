"""工具注册表 — 统一管理所有工具."""

from __future__ import annotations

from typing import Any, Callable

from backend.models.tool import ToolDefinition, ToolResult


class ToolRegistry:
    """工具注册表.
    
    统一管理内置工具、MCP工具等。
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        name: str,
        definition: ToolDefinition,
        handler: Callable[..., Any] | None = None,
    ) -> None:
        """注册工具.
        
        Args:
            name: 工具名称
            definition: 工具定义
            handler: 处理函数
        """
        self._tools[name] = definition
        if handler:
            self._handlers[name] = handler

    def unregister(self, name: str) -> None:
        """注销工具."""
        self._tools.pop(name, None)
        self._handlers.pop(name, None)

    def get_tool(self, name: str) -> ToolDefinition | None:
        """获取工具定义."""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Callable[..., Any] | None:
        """获取工具处理函数."""
        return self._handlers.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """列出所有工具."""
        return list(self._tools.values())

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在."""
        return name in self._tools

    def clear(self) -> None:
        """清空所有工具."""
        self._tools.clear()
        self._handlers.clear()


class ToolExecutor:
    """工具执行器."""

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry()

    async def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """执行工具.
        
        Args:
            name: 工具名称
            params: 参数
            
        Returns:
            ToolResult
        """
        if not self.registry.has_tool(name):
            return ToolResult(
                success=False,
                error=f"工具不存在: {name}",
            )
        
        handler = self.registry.get_handler(name)
        if not handler:
            return ToolResult(
                success=False,
                error=f"工具无处理函数: {name}",
            )
        
        try:
            import inspect
            if inspect.iscoroutinefunction(handler):
                result = await handler(**params)
            else:
                result = handler(**params)
            
            if isinstance(result, ToolResult):
                return result
            else:
                return ToolResult(
                    success=True,
                    output=str(result),
                )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"工具执行失败: {e}",
            )


def create_default_registry() -> ToolRegistry:
    """创建默认工具注册表.
    
    注册所有内置工具。
    """
    from backend.tools.cli.code_ops import CodeOperations
    from backend.tools.cli.file_ops import FileOperations
    from backend.tools.cli.shell_ops import ShellOperations

    registry = ToolRegistry()
    base_dir = "."  # 可通过配置修改

    # 文件操作工具
    file_ops = FileOperations(base_dir)
    
    registry.register(
        "file_read",
        ToolDefinition(
            name="file_read",
            description="读取文件内容，支持行号显示和分页",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "offset": {"type": "integer", "description": "起始行偏移", "default": 0},
                    "limit": {"type": "integer", "description": "最大读取行数"},
                },
                "required": ["path"],
            },
        ),
        file_ops.read,
    )
    
    registry.register(
        "file_write",
        ToolDefinition(
            name="file_write",
            description="写入文件内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"},
                    "append": {"type": "boolean", "description": "是否追加", "default": False},
                },
                "required": ["path", "content"],
            },
        ),
        file_ops.write,
    )
    
    registry.register(
        "file_search",
        ToolDefinition(
            name="file_search",
            description="在文件中搜索内容",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或正则"},
                    "path": {"type": "string", "description": "搜索路径", "default": "."},
                    "glob_pattern": {"type": "string", "description": "文件匹配模式", "default": "*"},
                },
                "required": ["query"],
            },
        ),
        file_ops.search,
    )
    
    registry.register(
        "list_dir",
        ToolDefinition(
            name="list_dir",
            description="列出目录内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径", "default": "."},
                    "recursive": {"type": "boolean", "description": "是否递归", "default": False},
                },
            },
        ),
        file_ops.list_dir,
    )

    # Shell操作工具
    shell_ops = ShellOperations(base_dir)
    
    registry.register(
        "shell_exec",
        ToolDefinition(
            name="shell_exec",
            description="执行Shell命令",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "working_dir": {"type": "string", "description": "工作目录"},
                    "timeout": {"type": "integer", "description": "超时(秒)"},
                },
                "required": ["command"],
            },
        ),
        shell_ops.execute,
    )
    
    registry.register(
        "git",
        ToolDefinition(
            name="git",
            description="执行Git命令",
            parameters={
                "type": "object",
                "properties": {
                    "subcommand": {"type": "string", "description": "git子命令"},
                    "args": {"type": "string", "description": "附加参数", "default": ""},
                    "working_dir": {"type": "string", "description": "工作目录"},
                },
                "required": ["subcommand"],
            },
        ),
        shell_ops.git,
    )

    # 代码分析工具
    code_ops = CodeOperations(base_dir)
    
    registry.register(
        "analyze_python",
        ToolDefinition(
            name="analyze_python",
            description="分析Python代码结构",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Python文件路径"},
                    "check_imports": {"type": "boolean", "default": True},
                    "check_functions": {"type": "boolean", "default": True},
                    "check_classes": {"type": "boolean", "default": True},
                },
                "required": ["path"],
            },
        ),
        code_ops.analyze_python,
    )
    
    registry.register(
        "find_todos",
        ToolDefinition(
            name="find_todos",
            description="查找代码中的TODO等标记",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "pattern": {"type": "string", "default": "TODO|FIXME|XXX|HACK"},
                },
            },
        ),
        code_ops.find_todos,
    )

    return registry

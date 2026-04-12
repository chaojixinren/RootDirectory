"""代码分析工具 — AST解析、代码质量检查等."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from backend.models.tool import ToolResult


class CodeOperations:
    """代码分析工具类."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """解析并验证路径."""
        target = (self.base_dir / path).resolve()
        try:
            target.relative_to(self.base_dir.resolve())
        except ValueError:
            raise ValueError(f"路径超出工作目录: {path}")
        return target

    async def analyze_python(
        self,
        path: str,
        check_imports: bool = True,
        check_functions: bool = True,
        check_classes: bool = True,
    ) -> ToolResult:
        """分析Python代码.
        
        Args:
            path: Python文件路径
            check_imports: 检查导入
            check_functions: 检查函数
            check_classes: 检查类
            
        Returns:
            ToolResult
        """
        try:
            target = self._resolve_path(path)
            
            if not target.exists():
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {path}",
                )
            
            content = target.read_text(encoding="utf-8")
            
            # 解析AST
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return ToolResult(
                    success=False,
                    error=f"Python语法错误: {e}",
                )
            
            # 收集信息
            analysis = {
                "imports": [],
                "functions": [],
                "classes": [],
                "issues": [],
            }
            
            for node in ast.walk(tree):
                # 导入
                if check_imports and isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            analysis["imports"].append(alias.name)
                    else:
                        module = node.module or ""
                        names = [a.name for a in node.names]
                        analysis["imports"].append(f"{module}: {', '.join(names)}")
                
                # 函数
                elif check_functions and isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args]
                    analysis["functions"].append({
                        "name": node.name,
                        "args": args,
                        "line": node.lineno,
                    })
                
                # 类
                elif check_classes and isinstance(node, ast.ClassDef):
                    methods = [
                        n.name for n in node.body 
                        if isinstance(n, ast.FunctionDef)
                    ]
                    analysis["classes"].append({
                        "name": node.name,
                        "methods": methods,
                        "line": node.lineno,
                    })
                
                # 安全问题检查
                elif isinstance(node, ast.Call):
                    # 检查 eval/exec
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ("eval", "exec"):
                            analysis["issues"].append({
                                "type": "security",
                                "message": f"发现危险函数调用: {node.func.id}",
                                "line": node.lineno,
                            })
                    # 检查 os.system/subprocess
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in ("system", "popen"):
                            analysis["issues"].append({
                                "type": "security",
                                "message": f"发现shell执行: {node.func.attr}",
                                "line": node.lineno,
                            })
            
            # 格式化输出
            output_lines = [f"Python代码分析: {path}\n"]
            
            if analysis["imports"]:
                output_lines.append(f"【导入】({len(analysis['imports'])}个)")
                for imp in analysis["imports"][:10]:
                    output_lines.append(f"  - {imp}")
                if len(analysis["imports"]) > 10:
                    output_lines.append(f"  ... 还有{len(analysis['imports']) - 10}个")
                output_lines.append("")
            
            if analysis["classes"]:
                output_lines.append(f"【类定义】({len(analysis['classes'])}个)")
                for cls in analysis["classes"][:5]:
                    methods_str = ", ".join(cls["methods"][:5])
                    if len(cls["methods"]) > 5:
                        methods_str += f"...等{len(cls['methods'])}个方法"
                    output_lines.append(f"  - {cls['name']} (行{cls['line']})")
                    output_lines.append(f"    方法: {methods_str}")
                output_lines.append("")
            
            if analysis["functions"]:
                output_lines.append(f"【函数定义】({len(analysis['functions'])}个)")
                for func in analysis["functions"][:10]:
                    args_str = ", ".join(func["args"])
                    output_lines.append(f"  - {func['name']}({args_str}) [行{func['line']}]")
                if len(analysis["functions"]) > 10:
                    output_lines.append(f"  ... 还有{len(analysis['functions']) - 10}个")
                output_lines.append("")
            
            if analysis["issues"]:
                output_lines.append(f"【问题】({len(analysis['issues'])}个)")
                for issue in analysis["issues"]:
                    output_lines.append(f"  [{issue['type'].upper()}] 行{issue['line']}: {issue['message']}")
            
            if not any([analysis["imports"], analysis["classes"], analysis["functions"], analysis["issues"]]):
                output_lines.append("(未检测到导入、类、函数或问题)")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=analysis,
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"分析失败: {e}",
            )

    async def find_todos(
        self,
        path: str = ".",
        pattern: str = r"TODO|FIXME|XXX|HACK",
    ) -> ToolResult:
        """查找代码中的TODO等标记.
        
        Args:
            path: 搜索路径
            pattern: 匹配模式
            
        Returns:
            ToolResult
        """
        try:
            target = self._resolve_path(path)
            
            todos = []
            file_count = 0
            
            for file_path in target.rglob("*"):
                if not file_path.is_file():
                    continue
                
                # 跳过二进制和大文件
                try:
                    if file_path.stat().st_size > 1024 * 1024:
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                
                file_count += 1
                lines = content.splitlines()
                
                for i, line in enumerate(lines, 1):
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        rel_path = file_path.relative_to(self.base_dir)
                        todos.append({
                            "file": str(rel_path),
                            "line": i,
                            "type": match.group(),
                            "content": line.strip()[:150],
                        })
                        
                        if len(todos) >= 100:
                            break
                
                if len(todos) >= 100:
                    break
            
            # 格式化输出
            if todos:
                output_lines = [f"找到 {len(todos)} 个标记 (搜索了 {file_count} 个文件):\n"]
                for todo in todos[:30]:
                    output_lines.append(f"{todo['file']}:{todo['line']} [{todo['type']}] {todo['content']}")
                if len(todos) > 30:
                    output_lines.append(f"\n... 还有 {len(todos) - 30} 个")
            else:
                output_lines = [f"未找到标记 (搜索了 {file_count} 个文件)"]
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "total": len(todos),
                    "files_searched": file_count,
                    "todos": todos[:30],
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

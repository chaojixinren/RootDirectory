"""文件操作工具 — 借鉴Claude Code的文件操作能力."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.models.tool import ToolResult


class FileOperations:
    """文件操作工具类.
    
    提供安全的文件读写、搜索等操作。
    """

    def __init__(self, base_dir: str | None = None):
        """初始化.
        
        Args:
            base_dir: 基础工作目录，所有操作限制在此目录下
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """解析并验证路径.
        
        确保路径在base_dir内，防止目录遍历攻击。
        """
        target = (self.base_dir / path).resolve()
        
        # 安全检查：确保在base_dir内
        try:
            target.relative_to(self.base_dir.resolve())
        except ValueError:
            raise ValueError(f"路径超出工作目录: {path}")
        
        return target

    async def read(
        self,
        path: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ToolResult:
        """读取文件内容.
        
        Args:
            path: 文件路径
            offset: 起始行偏移
            limit: 最大读取行数
            
        Returns:
            ToolResult包含文件内容
        """
        try:
            target = self._resolve_path(path)
            
            if not target.exists():
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {path}",
                )
            
            if not target.is_file():
                return ToolResult(
                    success=False,
                    error=f"路径不是文件: {path}",
                )
            
            # 读取文件
            content = target.read_text(encoding="utf-8")
            lines = content.splitlines()
            total_lines = len(lines)
            
            # 应用偏移和限制
            if offset > 0:
                lines = lines[offset:]
            if limit is not None:
                lines = lines[:limit]
            
            result_content = "\n".join(lines)
            
            # 添加行号
            numbered_lines = []
            for i, line in enumerate(lines, start=offset + 1):
                numbered_lines.append(f"{i:4d}| {line}")
            
            display_content = "\n".join(numbered_lines)
            
            return ToolResult(
                success=True,
                output=display_content,
                metadata={
                    "path": str(target),
                    "total_lines": total_lines,
                    "displayed_lines": len(lines),
                    "offset": offset,
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

    async def write(
        self,
        path: str,
        content: str,
        append: bool = False,
    ) -> ToolResult:
        """写入文件内容.
        
        Args:
            path: 文件路径
            content: 要写入的内容
            append: 是否追加模式
            
        Returns:
            ToolResult
        """
        try:
            target = self._resolve_path(path)
            
            # 确保父目录存在
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入内容
            mode = "a" if append else "w"
            target.write_text(content, encoding="utf-8")
            
            return ToolResult(
                success=True,
                output=f"文件已{'追加' if append else '写入'}: {path}",
                metadata={
                    "path": str(target),
                    "size": len(content),
                    "operation": "append" if append else "write",
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

    async def search(
        self,
        query: str,
        path: str = ".",
        glob_pattern: str = "*",
    ) -> ToolResult:
        """在文件中搜索内容.
        
        Args:
            query: 搜索关键词或正则表达式
            path: 搜索路径
            glob_pattern: 文件匹配模式
            
        Returns:
            ToolResult包含搜索结果
        """
        try:
            target_dir = self._resolve_path(path)
            
            if not target_dir.exists():
                return ToolResult(
                    success=False,
                    error=f"目录不存在: {path}",
                )
            
            results = []
            file_count = 0
            match_count = 0
            
            # 遍历文件
            for file_path in target_dir.rglob(glob_pattern):
                if not file_path.is_file():
                    continue
                
                # 跳过二进制文件和大文件
                try:
                    if file_path.stat().st_size > 1024 * 1024:  # 1MB
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                
                file_count += 1
                lines = content.splitlines()
                
                # 搜索匹配
                for i, line in enumerate(lines, 1):
                    if re.search(query, line, re.IGNORECASE):
                        match_count += 1
                        rel_path = file_path.relative_to(self.base_dir)
                        results.append({
                            "file": str(rel_path),
                            "line": i,
                            "content": line.strip()[:200],
                        })
                        
                        # 限制结果数量
                        if match_count >= 50:
                            break
                
                if match_count >= 50:
                    break
            
            # 格式化输出
            if results:
                output_lines = [f"找到 {match_count} 个匹配 (搜索了 {file_count} 个文件):\n"]
                for r in results[:20]:  # 最多显示20个
                    output_lines.append(f"{r['file']}:{r['line']}: {r['content']}")
                if match_count > 20:
                    output_lines.append(f"\n... 还有 {match_count - 20} 个匹配")
                output = "\n".join(output_lines)
            else:
                output = f"未找到匹配 (搜索了 {file_count} 个文件)"
            
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "query": query,
                    "files_searched": file_count,
                    "matches_found": match_count,
                    "results": results[:20],
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

    async def list_dir(
        self,
        path: str = ".",
        recursive: bool = False,
    ) -> ToolResult:
        """列出目录内容.
        
        Args:
            path: 目录路径
            recursive: 是否递归
            
        Returns:
            ToolResult
        """
        try:
            target = self._resolve_path(path)
            
            if not target.exists():
                return ToolResult(
                    success=False,
                    error=f"路径不存在: {path}",
                )
            
            if not target.is_dir():
                return ToolResult(
                    success=False,
                    error=f"路径不是目录: {path}",
                )
            
            items = []
            
            base_resolved = self.base_dir.resolve()

            if recursive:
                for item in target.rglob("*"):
                    rel_path = item.relative_to(base_resolved)
                    items.append({
                        "path": str(rel_path),
                        "type": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    })
            else:
                for item in target.iterdir():
                    items.append({
                        "name": item.name,
                        "type": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    })
            
            # 格式化输出
            output_lines = [f"目录: {path}\n"]
            for item in items[:50]:  # 限制数量
                if item["type"] == "dir":
                    output_lines.append(f"[D] {item.get('name', item.get('path', ''))}/")
                else:
                    size = item.get("size", 0) or 0
                    size_str = f"{size:,} B" if size < 1024 else f"{size/1024:.1f} KB"
                    output_lines.append(f"[F] {item.get('name', item.get('path', ''))} ({size_str})")
            
            if len(items) > 50:
                output_lines.append(f"\n... 还有 {len(items) - 50} 个条目")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "path": str(target),
                    "total_items": len(items),
                    "items": items[:50],
                },
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

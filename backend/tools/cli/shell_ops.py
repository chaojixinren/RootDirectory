"""Shell操作工具 — 借鉴Claude Code的shell执行能力."""

from __future__ import annotations

import asyncio
import functools
import os
import platform
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from backend.models.tool import ToolResult


class ShellOperations:
    """Shell操作工具类.
    
    提供安全的Shell命令执行。
    """

    # 危险命令黑名单
    DANGEROUS_COMMANDS = [
        "rm -rf /",
        "rm -rf /*",
        "> /dev/sda",
        "dd if=/dev/zero",
        "mkfs.",
        ":(){ :|:& };:",  # fork bomb
    ]

    def __init__(self, base_dir: str | None = None, timeout: int = 60):
        """初始化.
        
        Args:
            base_dir: 基础工作目录
            timeout: 命令执行超时(秒)
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.timeout = timeout

    _IS_WINDOWS = platform.system() == "Windows"

    # Linux → Windows 命令翻译表
    _LINUX_CMD_MAP = {
        "head": "more",
        "tail": "more",
        "cat": "type",
        "ls": "dir",
        "cp": "copy",
        "mv": "move",
        "rm": "del",
        "grep": "findstr",
        "which": "where",
        "touch": "echo.",
    }

    def _adapt_command_for_windows(self, command: str) -> str:
        """将命令适配为 Windows cmd.exe 兼容格式.

        主要处理：
        1. 将参数中的单引号替换为双引号 (cmd.exe 不识别单引号)
        2. 将管道后的 Linux 命令替换为 Windows 等价物
        3. 将 2>&1 等重定向适配为 Windows 格式
        """
        if not self._IS_WINDOWS:
            return command

        # 替换单引号包裹的参数为双引号
        # 例: curl -s 'https://example.com' → curl -s "https://example.com"
        result = re.sub(
            r"'([^']*?)'",
            r'"\1"',
            command,
        )

        # 处理管道后的 Linux 命令
        parts = result.split("|")
        adapted_parts = []
        for i, part in enumerate(parts):
            p = part.strip()
            if i > 0:  # 管道后的命令需要翻译
                for linux_cmd, win_cmd in self._LINUX_CMD_MAP.items():
                    # 匹配开头的命令词 (支持 head -100 等带参数的形式)
                    if re.match(rf"^{linux_cmd}\b", p):
                        # head -N → more (Windows more 不支持 -N，但至少能运行)
                        if linux_cmd in ("head", "tail"):
                            p = "more"  # Windows 的 more 会分页输出全部
                        else:
                            p = re.sub(rf"^{linux_cmd}\b", win_cmd, p)
                        break
            adapted_parts.append(p)
        result = " | ".join(adapted_parts)

        return result

    def _is_safe_command(self, command: str) -> tuple[bool, str]:
        """检查命令是否安全.
        
        Returns:
            (是否安全, 错误信息)
        """
        cmd_lower = command.lower()
        
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous.lower() in cmd_lower:
                return False, f"检测到危险命令: {dangerous}"
        
        return True, ""

    async def execute(
        self,
        command: str,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ToolResult:
        """执行Shell命令.
        
        Args:
            command: 要执行的命令
            working_dir: 工作目录
            env: 环境变量
            
        Returns:
            ToolResult
        """
        # 安全检查
        is_safe, error_msg = self._is_safe_command(command)
        if not is_safe:
            return ToolResult(
                success=False,
                error=error_msg,
            )

        # Windows 命令适配
        command = self._adapt_command_for_windows(command)
        
        # 解析工作目录
        if working_dir:
            work_path = (self.base_dir / working_dir).resolve()
            try:
                work_path.relative_to(self.base_dir.resolve())
            except ValueError:
                return ToolResult(
                    success=False,
                    error=f"工作目录超出范围: {working_dir}",
                )
        else:
            work_path = self.base_dir
        
        # 确保目录存在
        work_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # 使用 subprocess.run 在线程池中执行（兼容Windows上uvicorn的SelectorEventLoop）
            loop = asyncio.get_event_loop()
            completed = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    functools.partial(
                        subprocess.run,
                        command,
                        shell=True,
                        capture_output=True,
                        cwd=str(work_path),
                        env={**dict(os.environ), **(env or {})},
                        timeout=self.timeout,
                    ),
                ),
                timeout=self.timeout + 5,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            return ToolResult(
                success=False,
                error=f"命令执行超时(>{self.timeout}秒)",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"命令执行异常: {type(e).__name__}: {e}",
            )
        
        # 解析输出
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        
        # 限制输出长度
        max_output = 10000
        if len(stdout_str) > max_output:
            stdout_str = stdout_str[:max_output] + "\n... (输出已截断)"
        if len(stderr_str) > max_output:
            stderr_str = stderr_str[:max_output] + "\n... (输出已截断)"
        
        # 构建结果
        success = returncode == 0
        output_parts = []
        
        if stdout_str:
            output_parts.append(f"【标准输出】\n{stdout_str}")
        if stderr_str:
            output_parts.append(f"【错误输出】\n{stderr_str}")
        
        if output_parts:
            output = "\n\n".join(output_parts)
        elif not success:
            output = f"(命令返回退出码 {returncode}，无任何输出。可能是命令语法错误或网络问题)"
        else:
            output = "(无输出)"
        
        return ToolResult(
            success=success,
            output=output,
            error=stderr_str if not success else None,
            metadata={
                "command": command,
                "returncode": returncode,
                "working_dir": str(work_path),
                "stdout_length": len(stdout_str),
                "stderr_length": len(stderr_str),
            },
        )

    async def grep(
        self,
        pattern: str,
        path: str = ".",
        options: str = "",
    ) -> ToolResult:
        """使用grep搜索.
        
        Args:
            pattern: 搜索模式
            path: 搜索路径
            options: grep选项
            
        Returns:
            ToolResult
        """
        # 转义pattern中的特殊字符
        escaped_pattern = shlex.quote(pattern)
        command = f"grep -r {options} {escaped_pattern} {shlex.quote(path)} 2>/dev/null || true"
        
        return await self.execute(command)

    async def find(
        self,
        path: str = ".",
        name: str | None = None,
        type_filter: str | None = None,
    ) -> ToolResult:
        """使用find查找文件.
        
        Args:
            path: 起始路径
            name: 文件名模式
            type_filter: 类型过滤 (f=文件, d=目录)
            
        Returns:
            ToolResult
        """
        cmd_parts = ["find", shlex.quote(path)]
        
        if type_filter:
            cmd_parts.extend(["-type", type_filter])
        
        if name:
            cmd_parts.extend(["-name", shlex.quote(name)])
        
        cmd_parts.extend(["2>/dev/null", "|", "head", "-50"])
        
        command = " ".join(cmd_parts)
        return await self.execute(command)

    async def git(
        self,
        subcommand: str,
        args: str = "",
        working_dir: str | None = None,
    ) -> ToolResult:
        """执行git命令.
        
        Args:
            subcommand: git子命令
            args: 附加参数
            working_dir: 工作目录
            
        Returns:
            ToolResult
        """
        command = f"git {subcommand} {args}"
        return await self.execute(command, working_dir=working_dir)

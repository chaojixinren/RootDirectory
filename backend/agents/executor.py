"""执行专家Agent（Executor）— 负责执行具体任务."""

from __future__ import annotations

import json
from typing import Any

from backend.config.settings import get_settings
from backend.core.config_manager import get_config_manager
from backend.models.agent import AgentConfig, AgentResult, AgentRole
from backend.models.memory import Clue
from backend.tools.executor import ToolExecutor
from backend.tools.registry import ToolRegistry

from .base import BaseAgent


class ExecutorAgent(BaseAgent):
    """执行专家Agent — 负责执行具体任务并反馈结果.
    
    职责：
    1. 根据计划执行具体任务
    2. 调用工具完成操作
    3. 提取关键信息和线索
    4. 反馈执行结果和状态
    
    可以：
    - 使用工具完成任务
    - 派生子Agent并行处理（如需要）
    """

    ROLE_CONFIG_KEY = "executor"

    def __init__(
        self,
        config: AgentConfig | None = None,
        tool_registry: ToolRegistry | None = None,
        **kwargs: Any,
    ):
        if config is None:
            config = self._load_config_from_yaml()
        super().__init__(config, **kwargs)

        # 工具执行器
        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_executor = ToolExecutor(self.tool_registry)

        # 子Agent派生记录
        self.spawned_agents: list[dict[str, Any]] = []

    def _load_config_from_yaml(self) -> AgentConfig:
        """从agents.yaml加载配置."""
        config_manager = get_config_manager()
        agent_config = config_manager.get_agent_config(self.ROLE_CONFIG_KEY)

        if agent_config:
            return AgentConfig(
                role=AgentRole.EXECUTOR,
                name=agent_config.get("name", "执行专家"),
                model=agent_config.get("model", "gpt-4o-mini"),
                temperature=agent_config.get("temperature", 0.0),
                max_tokens=agent_config.get("max_tokens", 4000),
                max_steps=agent_config.get("max_steps", 20),
                system_prompt=agent_config.get("system_prompt", self._default_system_prompt()),
                can_spawn_children=True,
            )
        settings = get_settings()
        default_model = settings.llm.default_model or "gpt-4o-mini"
        return AgentConfig(
            role=AgentRole.EXECUTOR,
            name="执行专家",
            model=default_model,
            system_prompt=self._default_system_prompt(),
            can_spawn_children=True,
        )

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是执行专家（Executor），负责执行具体任务并反馈结果。

你的职责：
1. 根据任务描述，确定需要执行的具体操作
2. 通过tool_calls发出工具调用请求，系统会自动执行并返回结果
3. 提取关键信息和线索

可用工具：
- shell_exec: 执行shell命令（curl、nmap、wget、python等任何命令）
  参数: {"command": "要执行的命令"}
- file_read: 读取文件内容
  参数: {"path": "文件路径"}
- file_write: 写入文件内容
  参数: {"path": "文件路径", "content": "内容"}
- file_search: 搜索文件内容
  参数: {"query": "搜索关键词", "path": "搜索路径"}

⚠️ 重要提示 — 当前运行环境为 Windows：
- URL和路径参数必须用双引号包裹，不要用单引号
  正确: curl -s "https://example.com"
  错误: curl -s 'https://example.com'
- 不要使用 head、tail、grep 等Linux命令，改用Windows等效命令：
  head → more，grep → findstr，cat → type，ls → dir
- 管道输出截取用 more 代替 head
- 路径分隔符用反斜杠 \\ 或正斜杠 /

输出格式（必须严格JSON）：
{
  "status": "success|failed|partial",
  "summary": "执行摘要（一句话描述你要做什么）",
  "output": "你对任务的分析和说明",
  "clues": [
    {"key": "线索名", "value": "线索值", "confidence": 0.9, "category": "分类"}
  ],
  "tool_calls": [
    {"tool": "shell_exec", "params": {"command": "curl -s \"https://example.com\""}},
    {"tool": "shell_exec", "params": {"command": "nmap -sV target.com"}}
  ]
}

执行原则：
- tool_calls中只写要执行的工具和参数，不要写result字段（系统会自动执行并获取结果）
- 优先使用shell_exec工具执行信息收集命令（curl、wget、nmap等）
- 一次可以包含多个tool_calls
- 任务描述中如果提到具体命令，直接发出对应的tool_call
- 提取所有有价值的信息作为线索

始终输出合法的JSON格式。"""

    async def execute_task(
        self,
        task: str,
        available_tools: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行任务 — 核心执行方法.
        
        Args:
            task: 任务描述
            available_tools: 可用工具列表
            context: 上下文信息
            
        Returns:
            执行结果
        """
        # 构建执行提示词
        prompt = self._build_execute_prompt(task, available_tools, context)
        
        # 思考执行方案
        plan = await self.think_json(prompt)
        
        # 执行计划中的动作
        results = []
        tool_calls = []
        
        # 检查是否需要派生子Agent
        spawn_requests = plan.get("spawn_requests", [])
        if spawn_requests and self.config.can_spawn_children:
            # 记录派生请求，由上层处理
            self.spawned_agents.extend(spawn_requests)
        
        # 执行工具调用 — 同时支持"actions"和"tool_calls"两种格式
        # 格式1: actions: [{"type": "tool_call", "tool": ..., "params": ...}]
        actions = plan.get("actions", [])
        # 格式2: tool_calls: [{"tool": ..., "params": ...}]
        tc_from_plan = plan.get("tool_calls", [])
        if tc_from_plan and not actions:
            actions = [{"type": "tool_call", **tc} for tc in tc_from_plan]
        
        for action in actions:
            if not self.check_step_limit():
                break
            
            self.increment_step()
            
            action_type = action.get("type", "tool_call")
            if action_type == "tool_call":
                result = await self._execute_tool(action)
                tool_calls.append({
                    "tool": action.get("tool"),
                    "params": action.get("params"),
                    "result": result,
                })
                results.append(result)
            elif action_type == "think":
                # 思考步骤，记录但不执行
                results.append({"type": "think", "content": action.get("content")})
            elif action_type == "observe":
                # 观察步骤，记录结果
                results.append({"type": "observe", "content": action.get("content")})
        
        # 整合结果
        return {
            "status": plan.get("status", "partial"),
            "summary": plan.get("summary", "执行完成"),
            "output": "\n".join(str(r) for r in results),
            "clues": plan.get("clues", []),
            "tool_calls": tool_calls,
            "spawn_requests": spawn_requests,
            "steps_executed": self.current_step,
        }

    def _build_execute_prompt(
        self,
        task: str,
        available_tools: list[str] | None,
        context: dict[str, Any] | None,
    ) -> str:
        """构建执行提示词."""
        # 获取可用工具信息
        tools_info = []
        if available_tools:
            for tool_name in available_tools:
                tool_def = self.tool_registry.get_tool(tool_name)
                if tool_def:
                    tools_info.append(f"- {tool_name}: {tool_def.description}")
        
        prompt = f"""【执行任务】
{task}

【可用工具】
{chr(10).join(tools_info) if tools_info else "（使用通用工具）"}

"""
        
        if context:
            prompt += "【上下文信息】\n"
            for key, value in context.items():
                prompt += f"- {key}: {value}\n"
            prompt += "\n"
        
        prompt += f"""【当前步数】{self.current_step}/{self.max_steps}

请制定执行计划。如果需要：
1. 使用工具完成任务 — 在tool_calls中添加工具调用
2. 派生子Agent并行处理 — 在spawn_requests中添加请求
3. 记录关键信息 — 在clues中添加线索

请以JSON格式输出执行计划。"""
        
        return prompt

    async def _execute_tool(self, action: dict[str, Any]) -> Any:
        """执行工具调用."""
        tool_name = action.get("tool")
        params = action.get("params", {})
        
        try:
            result = await self.tool_executor.execute(tool_name, params)
            return result
        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    async def spawn_children(
        self,
        task_template: str,
        items: list[Any],
        max_children: int = 5,
    ) -> list[dict[str, Any]]:
        """派生子Agent并行处理.
        
        例如：
        - 端口扫描：items=[80, 443, 8080], task_template="扫描端口 {item}"
        - 目录扫描：items=["/admin", "/api"], task_template="扫描目录 {item}"
        
        Args:
            task_template: 任务模板，包含{item}占位符
            items: 要处理的物品列表
            max_children: 最大子Agent数
            
        Returns:
            子Agent派生请求列表
        """
        spawn_requests = []
        
        for item in items[:max_children]:
            task = task_template.replace("{item}", str(item))
            spawn_requests.append({
                "task": task,
                "role": "executor",
                "parent_id": self.agent_id,
                "context": {"item": item},
            })
        
        self.spawned_agents.extend(spawn_requests)
        return spawn_requests

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行入口（简化接口）."""
        available_tools = None
        if context:
            available_tools = context.get("available_tools")
        
        result = await self.execute_task(
            task=task,
            available_tools=available_tools,
            context=context,
        )
        
        # 提取线索
        for clue_data in result.get("clues", []):
            self.add_clue(
                key=clue_data.get("key", "unknown"),
                value=clue_data.get("value", ""),
                confidence=clue_data.get("confidence", 1.0),
            )
        
        # 构建结果
        agent_result = self.to_result(
            status=result.get("status", "partial"),
            summary=result.get("summary", "执行完成"),
            output=result.get("output", ""),
        )
        
        # 添加工具调用记录
        agent_result.tool_calls = result.get("tool_calls", [])
        
        # 如果有子Agent派生请求，添加到线索
        if self.spawned_agents:
            agent_result.clues.append({
                "key": "spawn_requests",
                "value": json.dumps(self.spawned_agents, ensure_ascii=False),
            })
        
        return agent_result

    def reset(self) -> None:
        """重置执行状态."""
        super().reset()
        self.spawned_agents = []

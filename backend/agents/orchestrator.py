"""决策Agent（Orchestrator）— 任务接收、理解、拆分、调度."""

from __future__ import annotations

import json
from typing import Any

from backend.core.config_manager import get_config_manager
from backend.models.agent import AgentConfig, AgentResult, AgentRole
from backend.models.task import SubTask, SubTaskStatus

from .base import BaseAgent


class OrchestratorAgent(BaseAgent):
    """决策Agent — 负责任务的接收、理解、拆分和调度.
    
    职责：
    1. 接收用户任务，理解任务目标和约束
    2. 将任务拆分为可执行的子任务
    3. 为每个子任务分配合适的专家Agent（Thinker/Executor）
    4. 动态调整执行步数，避免死循环
    5. 整合执行结果，判断任务是否完成
    
    不直接执行任务，只负责决策和调度.
    """

    ROLE_CONFIG_KEY = "orchestrator"

    def __init__(self, config: AgentConfig | None = None, **kwargs: Any):
        if config is None:
            config = self._load_config_from_yaml()
        super().__init__(config, **kwargs)
        
        # 任务历史，用于死循环检测
        self._task_history: list[str] = []
        self._no_progress_count = 0  # 无进展计数

    def _load_config_from_yaml(self) -> AgentConfig:
        """从agents.yaml加载配置."""
        config_manager = get_config_manager()
        agent_config = config_manager.get_agent_config(self.ROLE_CONFIG_KEY)

        if agent_config:
            return AgentConfig(
                role=AgentRole.ORCHESTRATOR,
                name=agent_config.get("name", "协调指挥官"),
                model=agent_config.get("model", "gpt-4o"),
                temperature=agent_config.get("temperature", 0.5),
                max_tokens=agent_config.get("max_tokens", 8000),
                max_steps=agent_config.get("max_steps", 15),
                system_prompt=agent_config.get("system_prompt", self._default_system_prompt()),
            )
        return AgentConfig(
            role=AgentRole.ORCHESTRATOR,
            name="决策Agent",
            system_prompt=self._default_system_prompt(),
        )

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是决策Agent（Orchestrator），负责任务的接收、理解、拆分和调度。

你的职责：
1. 接收用户任务，理解任务目标和约束
2. 将任务拆分为可执行的子任务
3. 为每个子任务分配合适的专家Agent
4. 动态调整执行步数，避免死循环
5. 整合执行结果，判断任务是否完成

你不直接执行任务，只负责决策和调度。

【重要】Agent角色能力说明：
- executor（执行专家）：唯一能执行实际操作的Agent。可以执行shell命令（curl、nmap、wget等）、读写文件、运行代码。所有需要与目标交互的操作（信息收集、扫描探测、漏洞利用、payload发送等）必须分配给executor。
- thinker（思考专家）：负责深度分析和策略规划，不能执行任何操作。
- web_security / network_penetration / code_auditor / mobile_security / security_ops（安全专家）：只能提供专业的安全分析建议和理论指导，不能执行任何操作。

【调度原则】
1. 需要执行命令、访问URL、发送请求、扫描端口等操作时，必须分配给 executor
2. 安全专家仅负责制定攻击方案、分析结果、提供专业建议
3. 每轮至少要有一个 executor 任务来推进实际进展
4. 信息收集阶段：executor执行curl/nmap等 + 安全专家分析结果
5. 漏洞利用阶段：executor执行payload + 安全专家指导方向

【禁止重复探测规则】
- 上一轮已经获取的信息（页面内容、WAF规则、响应头等）不得重复获取
- 如果上轮已拿到页面内容，本轮必须基于已有信息推进下一步（构造payload、尝试绕过、发送攻击等）
- 每轮的executor任务描述必须包含具体的命令或payload，不能只写“探测页面”“获取信息”等模糊指令
- 第1轮收集信息，第2轮必须开始攻击尝试

输出格式（JSON）：
{
  "analysis": "任务分析：理解任务目标、约束条件和当前进展",
  "sub_tasks": [
    {
      "description": "子任务描述（对executor任务要包含具体的命令或操作）",
      "assigned_role": "executor|thinker|web_security|...",
      "max_steps": 10,
      "reason": "为什么分配给这个角色"
    }
  ],
  "plan_adjustment": "如果有，说明对计划的调整",
  "should_continue": true,
  "is_completed": false,
  "progress_assessment": "进度评估：已完成、进行中、阻塞",
  "reason": "决策理由"
}

死循环检测规则：
- 如果发现任务在重复之前的步骤，标记为潜在死循环
- 建议调整策略或引入反思Agent
- 动态减少子任务的max_steps

始终输出合法的JSON格式。"""

    async def plan(
        self,
        goal: str,
        round_index: int,
        memory_text: str,
        previous_results: list[dict[str, Any]],
        available_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """制定计划 — 核心决策方法.
        
        Args:
            goal: 任务目标
            round_index: 当前轮次
            memory_text: 记忆文本
            previous_results: 之前的执行结果
            available_agents: 可用Agent列表
            
        Returns:
            决策结果，包含子任务分配
        """
        # 构建决策提示词
        prompt = self._build_plan_prompt(
            goal=goal,
            round_index=round_index,
            memory_text=memory_text,
            previous_results=previous_results,
            available_agents=available_agents,
        )
        
        # 调用LLM获取决策
        response = await self.think_json(prompt)
        
        # 保存决策历史
        self._task_history.append(json.dumps(response, ensure_ascii=False))
        
        # 检测死循环
        if self._detect_loop():
            response["potential_loop"] = True
            response["suggestion"] = "检测到潜在死循环，建议触发反思Agent"
        
        return response

    def _build_plan_prompt(
        self,
        goal: str,
        round_index: int,
        memory_text: str,
        previous_results: list[dict[str, Any]],
        available_agents: list[str] | None = None,
    ) -> str:
        """构建计划提示词."""
        prompt = f"""【任务目标】
{goal}

【当前信息】
- 当前轮次: {round_index}
- 可用Agent: {', '.join(available_agents or ['thinker', 'executor'])}

【记忆摘要】
{memory_text or '（无记忆）'}

"""
        
        if previous_results:
            prompt += "【上一轮执行结果】\n"
            for i, result in enumerate(previous_results, 1):
                prompt += f"{i}. [{result.get('role', 'unknown')}] {result.get('summary', '无摘要')}\n"
                # 显示工具执行的实际结果（关键信息）
                if result.get('tool_results'):
                    for tr in result['tool_results']:
                        params_str = json.dumps(tr.get('params', {}), ensure_ascii=False)
                        success_mark = '✅' if tr.get('success') else '❌'
                        prompt += f"   {success_mark} 工具[{tr.get('tool')}] {params_str}\n"
                        out = tr.get('output', '')
                        if out:
                            # 截取关键输出，避免过长
                            if len(out) > 1500:
                                out = out[:1500] + '... (已截断)'
                            prompt += f"   输出: {out}\n"
                elif result.get('output'):
                    out = result['output']
                    if len(out) > 1500:
                        out = out[:1500] + '... (已截断)'
                    prompt += f"   输出: {out}\n"
                if result.get('clues'):
                    prompt += f"   线索: {result['clues']}\n"
        else:
            prompt += "【上一轮执行结果】\n（首次执行，无历史结果）\n"
        
        prompt += """
请基于以上信息，制定本轮执行计划。

要求：
1. 仔细阅读上一轮的工具执行输出，提取关键发现
2. 【禁止重复】如果上一轮已经获取了页面内容/响应头/WAF信息，本轮绝不能再发同样的请求
3. 基于已有信息推进攻击：构造payload、尝试绕过、发送exploit
4. 给executor的任务描述必须包含具体的命令或payload（如：curl -X POST "url" -d "payload"），不能只写"探测页面"
5. 为每个子任务选择合适的Agent角色
6. 如果任务已完成（如已获取flag），设置is_completed为true
7. 【重要】需要执行shell命令、发送HTTP请求等操作时，必须分配给executor
8. 安全专家和thinker只能做分析和规划，不能执行操作
9. 每轮至少安排一个executor任务来推进实际进展

你必须严格按照以下JSON格式输出（不要使用其他格式）：
```json
{
  "analysis": "任务分析",
  "sub_tasks": [
    {
      "description": "子任务描述",
      "assigned_role": "thinker或executor",
      "max_steps": 10,
      "reason": "分配理由"
    }
  ],
  "should_continue": true,
  "is_completed": false,
  "reason": "决策理由"
}
```

注意：sub_tasks 数组不能为空（除非 is_completed 为 true）。assigned_role 只能是 """ + ", ".join(available_agents or ["thinker", "executor"]) + "。"
        
        return prompt

    def _detect_loop(self) -> bool:
        """检测潜在死循环.
        
        通过比较最近的历史决策来检测重复模式.
        """
        if len(self._task_history) < 3:
            return False
        
        # 检查最近3个决策是否高度相似
        recent = self._task_history[-3:]
        if len(set(recent)) < 3:
            self._no_progress_count += 1
            return self._no_progress_count >= 2
        
        # 检查关键词重复
        last = self._task_history[-1]
        keywords = ["重试", "再次", "重新", "repeat", "retry"]
        if any(kw in last for kw in keywords):
            self._no_progress_count += 1
            return self._no_progress_count >= 2
        
        self._no_progress_count = max(0, self._no_progress_count - 1)
        return False

    def parse_sub_tasks(self, plan_result: dict[str, Any]) -> list[SubTask]:
        """解析计划结果为子任务列表."""
        sub_tasks = []
        
        for i, task_data in enumerate(plan_result.get("sub_tasks", []), 1):
            # 动态调整步数
            suggested_steps = task_data.get("max_steps", 10)
            
            # 如果检测到死循环，减少步数
            if plan_result.get("potential_loop"):
                suggested_steps = max(5, suggested_steps // 2)
            
            sub_task = SubTask(
                description=task_data["description"],
                assigned_to=None,  # 由调度器后续分配
                agent_role=task_data.get("assigned_role", "executor"),
                max_steps=min(suggested_steps, 20),  # 上限20
                metadata={
                    "reason": task_data.get("reason", ""),
                    "plan_adjustment": plan_result.get("plan_adjustment", ""),
                },
            )
            sub_tasks.append(sub_task)
        
        return sub_tasks

    async def evaluate_completion(
        self,
        goal: str,
        all_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """评估任务是否完成."""
        prompt = f"""【任务目标】
{goal}

【所有执行结果】
"""
        for result in all_results:
            prompt += f"- {result.get('role', 'unknown')}: {result.get('summary', '')}\n"
        
        prompt += """
请评估任务是否已完成。

输出格式（JSON）：
{
  "is_completed": true|false,
  "completion_percentage": 0-100,
  "assessment": "评估说明",
  "remaining_work": "如果未完成，说明剩余工作",
  "final_answer": "如果已完成，提供最终答案摘要"
}
"""
        
        return await self.think_json(prompt)

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行调度决策（简化接口）."""
        context = context or {}
        
        plan_result = await self.plan(
            goal=task,
            round_index=context.get("round_index", 0),
            memory_text=context.get("memory_text", ""),
            previous_results=context.get("previous_results", []),
            available_agents=context.get("available_agents"),
        )
        
        # 构建结果
        sub_tasks = self.parse_sub_tasks(plan_result)
        
        summary = plan_result.get("analysis", "决策完成")
        if plan_result.get("potential_loop"):
            summary += " [警告：检测到潜在死循环]"
        
        result = self.to_result(
            status="success",
            summary=summary,
            output=json.dumps(plan_result, ensure_ascii=False, indent=2),
        )
        
        # 添加子任务信息到结果
        result.clues.append({
            "key": "sub_tasks",
            "value": json.dumps([s.model_dump(mode="json") for s in sub_tasks], ensure_ascii=False),
        })
        result.clues.append({
            "key": "should_continue",
            "value": str(plan_result.get("should_continue", True)),
        })
        result.clues.append({
            "key": "is_completed",
            "value": str(plan_result.get("is_completed", False)),
        })
        
        return result

    def reset(self) -> None:
        """重置Orchestrator状态."""
        super().reset()
        self._task_history = []
        self._no_progress_count = 0

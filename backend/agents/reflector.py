"""反思Agent（Reflector）— 基于记忆做反思和改进."""

from __future__ import annotations

from typing import Any

from backend.core.config_manager import get_config_manager
from backend.models.agent import AgentConfig, AgentResult, AgentRole
from backend.models.memory import MemoryDigest

from .base import BaseAgent


class ReflectorAgent(BaseAgent):
    """反思Agent — 负责审视执行过程，发现问题和改进点.
    
    职责：
    1. 分析任务执行历史
    2. 识别进度停滞的原因
    3. 发现策略和方案的不足
    4. 提供改进建议
    
    触发条件：
    - 任务多轮无进展
    - 频繁出现相同错误
    - 决策Agent请求反思
    """

    ROLE_CONFIG_KEY = "reflector"

    def __init__(self, config: AgentConfig | None = None, **kwargs: Any):
        if config is None:
            config = self._load_config_from_yaml()
        super().__init__(config, **kwargs)
        
        # 反思历史
        self._reflection_history: list[dict[str, Any]] = []

    def _load_config_from_yaml(self) -> AgentConfig:
        """从agents.yaml加载配置."""
        config_manager = get_config_manager()
        agent_config = config_manager.get_agent_config(self.ROLE_CONFIG_KEY)

        if agent_config:
            return AgentConfig(
                role=AgentRole.REFLECTOR,
                name=agent_config.get("name", "反思专家"),
                model=agent_config.get("model", "gpt-4o"),
                temperature=agent_config.get("temperature", 0.3),
                max_tokens=agent_config.get("max_tokens", 8000),
                max_steps=agent_config.get("max_steps", 10),
                system_prompt=agent_config.get("system_prompt", self._default_system_prompt()),
            )
        return AgentConfig(
            role=AgentRole.REFLECTOR,
            name="反思Agent",
            system_prompt=self._default_system_prompt(),
        )

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是反思Agent（Reflector），负责审视执行过程，发现问题和改进点。

你的职责：
1. 分析任务执行历史，找出模式和趋势
2. 识别进度停滞的根本原因
3. 发现策略和方案的不足之处
4. 提供具体可行的改进建议

反思原则：
- 客观公正：基于事实，不预设立场
- 深入本质：找到问题的根本原因，而非表面现象
- 建设性：提供可执行的改进方案
- 系统性：考虑整体流程和各个Agent的协作

反思维度：
1. 任务理解：目标是否清晰？约束是否合理？
2. 计划制定：计划是否可行？资源分配是否合理？
3. 执行质量：执行是否到位？错误处理是否恰当？
4. 协作效率：Agent间协作是否顺畅？
5. 信息流动：线索和记忆是否有效利用？

输出格式（JSON）：
{
  "observation": {
    "execution_pattern": "执行模式描述",
    "stagnation_point": "停滞点分析",
    "error_pattern": "错误模式"
  },
  "problems": [
    {
      "category": "任务理解|计划制定|执行质量|协作效率|信息流动",
      "description": "问题描述",
      "severity": "low|medium|high|critical",
      "evidence": ["证据1", "证据2"]
    }
  ],
  "root_cause_analysis": "根本原因分析",
  "suggestions": [
    {
      "target": "建议对象: orchestrator|thinker|executor",
      "action": "具体行动建议",
      "expected_outcome": "预期效果",
      "priority": "low|medium|high"
    }
  ],
  "should_adjust_strategy": true,
  "new_strategy": "如果需要调整策略，提供新策略"
}

始终输出合法的JSON格式。"""

    def should_reflect(
        self,
        round_index: int,
        recent_rounds: list[dict[str, Any]],
        stall_threshold: int = 3,
    ) -> bool:
        """检查是否需要触发反思.
        
        Args:
            round_index: 当前轮次
            recent_rounds: 最近几轮的结果
            stall_threshold: 停滞阈值（轮数）
            
        Returns:
            是否需要反思
        """
        if round_index < 1:
            return False
        
        if len(recent_rounds) < 1:
            return False
        
        # 检查最近N轮是否有实质进展
        # 通过比较结果摘要的相似度来判断
        recent_summaries = [
            r.get("orchestrator_plan", "")[-100:]  # 取最后100字符
            for r in recent_rounds[-stall_threshold:]
        ]
        
        # 如果所有摘要都相似，说明没有进展
        if len(set(recent_summaries)) == 1:
            return True
        
        # 检查错误模式
        error_count = sum(
            1 for r in recent_rounds[-stall_threshold:]
            if any(
                ar.get("status") == "failed"
                for ar in r.get("agent_results", [])
            )
        )
        
        # 如果最近N轮都有错误，触发反思
        if error_count >= stall_threshold:
            return True
        
        return False

    async def reflect(
        self,
        goal: str,
        memory: MemoryDigest | None,
        rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """执行反思.
        
        Args:
            goal: 任务目标
            memory: 记忆摘要
            rounds: 所有执行轮次
            
        Returns:
            反思结果
        """
        prompt = self._build_reflection_prompt(goal, memory, rounds)
        return await self.think_json(prompt)

    def _build_reflection_prompt(
        self,
        goal: str,
        memory: MemoryDigest | None,
        rounds: list[dict[str, Any]],
    ) -> str:
        """构建反思提示词."""
        prompt = f"""【任务目标】
{goal}

"""
        
        if memory and not memory.is_empty():
            prompt += f"【记忆摘要】\n{memory.to_prompt_text()}\n\n"
        
        # 构建执行历史摘要
        prompt += "【执行历史】\n"
        for i, round_data in enumerate(rounds[-5:], 1):  # 最近5轮
            prompt += f"\n--- 轮次 {i} ---\n"
            prompt += f"计划: {round_data.get('orchestrator_plan', '无')[:200]}...\n"
            
            for ar in round_data.get("agent_results", []):
                prompt += f"- {ar.get('role', 'unknown')}: {ar.get('status')} - {ar.get('summary', '无')[:100]}\n"
        
        prompt += """
请基于以上信息，进行深入反思。

要求：
1. 客观分析执行过程中的问题和模式
2. 找出进度停滞的根本原因
3. 评估各Agent的表现和协作效率
4. 提供具体、可执行的改进建议
5. 如果需要，提出新的策略方向
"""
        
        return prompt

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行反思（简化接口）."""
        context = context or {}
        
        result = await self.reflect(
            goal=task,
            memory=context.get("memory"),
            rounds=context.get("rounds", []),
        )
        
        # 保存反思历史
        self._reflection_history.append(result)
        
        # 提取关键信息
        problems = result.get("problems", [])
        suggestions = result.get("suggestions", [])
        
        summary = f"发现问题: {len(problems)}个, 建议: {len(suggestions)}个"
        if result.get("should_adjust_strategy"):
            summary += " [建议调整策略]"
        
        return self.to_result(
            status="success",
            summary=summary,
            output=result,
        )

    def get_reflection_summary(self, n: int = 3) -> str:
        """获取最近N次反思的摘要."""
        if not self._reflection_history:
            return "无反思记录"
        
        summaries = []
        for r in self._reflection_history[-n:]:
            problems = r.get("problems", [])
            if problems:
                summaries.append(f"发现{len(problems)}个问题")
        
        return "; ".join(summaries) if summaries else "无问题记录"

    def reset(self) -> None:
        """重置反思状态."""
        super().reset()
        self._reflection_history = []

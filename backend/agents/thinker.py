"""思考专家Agent（Thinker）— 提供解决方案和思考."""

from __future__ import annotations

import json
from typing import Any

from backend.config.settings import get_settings
from backend.core.config_manager import get_config_manager
from backend.models.agent import AgentConfig, AgentResult, AgentRole
from backend.models.memory import Clue

from .base import BaseAgent


class ThinkerAgent(BaseAgent):
    """思考专家Agent — 负责分析问题、设计方案和评估风险.
    
    职责：
    1. 深入分析问题本质
    2. 设计可行的解决方案
    3. 评估方案的风险和收益
    4. 提供清晰的思考过程
    
    不直接执行代码或命令，只负责思考和建议.
    """

    ROLE_CONFIG_KEY = "thinker"

    def __init__(self, config: AgentConfig | None = None, **kwargs: Any):
        if config is None:
            config = self._load_config_from_yaml()
        super().__init__(config, **kwargs)

    def _load_config_from_yaml(self) -> AgentConfig:
        """从agents.yaml加载配置."""
        config_manager = get_config_manager()
        agent_config = config_manager.get_agent_config(self.ROLE_CONFIG_KEY)

        if agent_config:
            return AgentConfig(
                role=AgentRole.THINKER,
                name=agent_config.get("name", "思考专家"),
                model=agent_config.get("model", "gpt-4o"),
                temperature=agent_config.get("temperature", 0.0),
                max_tokens=agent_config.get("max_tokens", 4000),
                max_steps=agent_config.get("max_steps", 15),
                system_prompt=agent_config.get("system_prompt", self._default_system_prompt()),
            )
        settings = get_settings()
        default_model = settings.llm.default_model or "gpt-4o"
        return AgentConfig(
            role=AgentRole.THINKER,
            name="思考专家",
            model=default_model,
            system_prompt=self._default_system_prompt(),
        )

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是思考专家（Thinker），负责分析问题、设计方案和评估风险。

你的职责：
1. 深入分析问题本质，找出核心矛盾
2. 设计可行的解决方案，考虑多种可能性
3. 评估每个方案的风险和收益
4. 提供清晰的思考过程和推理依据

你不直接执行代码或命令，只负责思考和建议。

思考原则：
- 结构化思考：将复杂问题分解为可管理的部分
- 多角度分析：从技术、业务、安全等角度思考
- 假设验证：对关键假设进行验证
- 权衡取舍：评估不同方案的优缺点

输出格式（JSON）：
{
  "analysis": {
    "problem_breakdown": ["问题分解1", "问题分解2"],
    "key_challenges": ["关键挑战1", "关键挑战2"],
    "assumptions": ["假设1", "假设2"]
  },
  "solutions": [
    {
      "approach": "方案描述",
      "pros": ["优点1", "优点2"],
      "cons": ["缺点1", "缺点2"],
      "risks": ["风险1", "风险2"],
      "complexity": "low|medium|high",
      "recommendation": "推荐程度(1-10)"
    }
  ],
  "recommended_solution": "推荐方案编号",
  "reasoning": "推荐理由",
  "next_steps": ["下一步行动1", "下一步行动2"],
  "clues": [
    {"key": "线索名", "value": "线索值", "confidence": 0.9}
  ]
}

始终输出合法的JSON格式。"""

    async def deep_think(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
        constraints: list[str] | None = None,
    ) -> dict[str, Any]:
        """深度思考 — 核心思考方法.
        
        Args:
            problem: 要解决的问题
            context: 上下文信息
            constraints: 约束条件
            
        Returns:
            思考结果
        """
        prompt = self._build_think_prompt(problem, context, constraints)
        return await self.think_json(prompt)

    def _build_think_prompt(
        self,
        problem: str,
        context: dict[str, Any] | None,
        constraints: list[str] | None,
    ) -> str:
        """构建思考提示词."""
        prompt = f"""【问题】
{problem}

"""
        
        if context:
            prompt += "【上下文信息】\n"
            for key, value in context.items():
                prompt += f"- {key}: {value}\n"
            prompt += "\n"
        
        if constraints:
            prompt += "【约束条件】\n"
            for c in constraints:
                prompt += f"- {c}\n"
            prompt += "\n"
        
        prompt += """请深入思考这个问题，提供结构化的分析和解决方案。

要求：
1. 将问题分解为多个部分进行分析
2. 提供2-3个可行的解决方案
3. 对每个方案进行风险评估
4. 给出明确的推荐和理由
5. 提取关键线索用于后续执行
"""
        
        return prompt

    async def analyze_risk(
        self,
        solution: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """风险评估 — 对特定方案进行风险分析."""
        prompt = f"""【待评估方案】
{solution}

"""
        if context:
            prompt += f"【上下文】\n{context}\n\n"
        
        prompt += """请对这个方案进行详细的风险评估。

输出格式（JSON）：
{
  "risk_level": "low|medium|high|critical",
  "risks": [
    {
      "category": "技术|安全|业务|合规",
      "description": "风险描述",
      "probability": "low|medium|high",
      "impact": "low|medium|high",
      "mitigation": "缓解措施"
    }
  ],
  "overall_assessment": "总体评估",
  "recommendations": ["建议1", "建议2"]
}
"""
        
        return await self.think_json(prompt)

    async def compare_solutions(
        self,
        solutions: list[dict[str, Any]],
        criteria: list[str] | None = None,
    ) -> dict[str, Any]:
        """方案对比 — 对比多个解决方案."""
        solutions_text = "\n\n".join(
            f"方案{i+1}: {s}" for i, s in enumerate(solutions)
        )
        
        criteria_text = ", ".join(criteria) if criteria else "可行性、风险、成本、时间"
        
        prompt = f"""【待对比方案】
{solutions_text}

【评估标准】
{criteria_text}

请对比这些方案，给出综合评估。

输出格式（JSON）：
{{
  "comparison_matrix": {{
    "方案1": {{"可行性": 8, "风险": 3, "成本": 5}},
    "方案2": {{"可行性": 6, "风险": 5, "成本": 8}}
  }},
  "best_choice": "推荐方案",
  "reasoning": "选择理由",
  "trade_offs": "需要权衡的因素"
}}
"""
        
        return await self.think_json(prompt)

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行思考任务（简化接口）."""
        # 解析任务和约束
        constraints = None
        if context:
            constraints = context.get("constraints")
        
        # 执行思考
        result = await self.deep_think(
            problem=task,
            context=context,
            constraints=constraints,
        )
        
        # 提取线索
        if "clues" in result:
            for clue_data in result["clues"]:
                self.add_clue(
                    key=clue_data.get("key", "unknown"),
                    value=clue_data.get("value", ""),
                    confidence=clue_data.get("confidence", 1.0),
                )
        
        # 构建结果
        summary = result.get("reasoning", "思考完成")
        recommended = result.get("recommended_solution", "")
        if recommended:
            summary += f" [推荐方案: {recommended}]"
        
        return self.to_result(
            status="success",
            summary=summary,
            output=json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, dict) else str(result),
        )

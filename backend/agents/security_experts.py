"""安全专家Agent实现 — 基于agents.yaml配置的各类安全专家."""

from __future__ import annotations

from typing import Any

from backend.core.config_manager import get_config_manager
from backend.models.agent import AgentConfig, AgentResult, AgentRole

from .base import BaseAgent


class SecurityExpertAgent(BaseAgent):
    """安全专家Agent基类.

    从agents.yaml加载配置，实现特定领域的安全专家。
    """

    ROLE_CONFIG_KEY: str = ""  # 子类必须定义

    def __init__(self, config: AgentConfig | None = None, **kwargs: Any):
        if config is None:
            config = self._load_config_from_yaml()
        super().__init__(config, **kwargs)

    def _load_config_from_yaml(self) -> AgentConfig:
        """从agents.yaml加载配置."""
        config_manager = get_config_manager()
        agent_config = config_manager.get_agent_config(self.ROLE_CONFIG_KEY)

        if not agent_config:
            # 如果配置不存在，使用默认配置
            return AgentConfig(
                role=AgentRole(self.ROLE_CONFIG_KEY),
                name=self.ROLE_CONFIG_KEY,
                system_prompt=f"You are a {self.ROLE_CONFIG_KEY} expert.",
            )

        # 从YAML配置构建AgentConfig
        return AgentConfig(
            role=AgentRole(self.ROLE_CONFIG_KEY),
            name=agent_config.get("name", self.ROLE_CONFIG_KEY),
            model=agent_config.get("model", "gpt-4o"),
            temperature=agent_config.get("temperature", 0.1),
            max_tokens=agent_config.get("max_tokens", 4000),
            max_steps=agent_config.get("max_steps", 20),
            system_prompt=agent_config.get("system_prompt", ""),
        )

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行安全分析任务."""
        context = context or {}

        # 构建任务提示词
        prompt = self._build_task_prompt(task, context)

        # 调用LLM进行安全分析
        result = await self.think(prompt)

        # 构建结果
        return self.to_result(
            status="success",
            summary=f"[{self.name}] 完成安全分析",
            output=result,
        )

    def _build_task_prompt(self, task: str, context: dict[str, Any]) -> str:
        """构建任务提示词."""
        prompt = f"""【安全测试任务】
{task}

"""

        # 添加上下文信息
        if context.get("goal"):
            prompt += f"【整体目标】\n{context['goal']}\n\n"

        if context.get("memory"):
            prompt += f"【历史分析结果】\n{context['memory']}\n\n"

        if context.get("other_expert_results"):
            prompt += "【其他专家分析结果】\n"
            for expert, result in context["other_expert_results"].items():
                prompt += f"- {expert}: {result[:200]}...\n"
            prompt += "\n"

        prompt += """请基于你的专业领域，进行深入的安全分析。

要求：
1. 关注你专业领域内的关键安全风险
2. 识别高价值攻击面或防御漏洞
3. 提供具体的验证建议和修复方案
4. 与其他专家协同，形成完整的安全评估
"""

        return prompt


class WebSecurityExpert(SecurityExpertAgent):
    """Web安全专家.

    专注于Web应用、API、认证系统、业务逻辑漏洞分析。
    """

    ROLE_CONFIG_KEY = "web_security"

    def _build_task_prompt(self, task: str, context: dict[str, Any]) -> str:
        """构建Web安全专家任务提示词."""
        prompt = super()._build_task_prompt(task, context)
        prompt += """
额外要求：
- 重点关注：认证与会话、授权与越权、输入处理、浏览器侧风险、业务逻辑
- 分析攻击面时识别高价值突破点
- 为其他专家提供Web攻击面判断和验证优先级
"""
        return prompt


class NetworkPenetrationExpert(SecurityExpertAgent):
    """网络渗透专家.

    专注于主机发现、端口扫描、服务识别、网络边界分析和内网渗透。
    """

    ROLE_CONFIG_KEY = "network_penetration"

    def _build_task_prompt(self, task: str, context: dict[str, Any]) -> str:
        """构建网络渗透专家任务提示词."""
        prompt = super()._build_task_prompt(task, context)
        prompt += """
额外要求：
- 重点关注：资产暴露、服务识别、网络突破链、横向移动、边界ACL
- 识别最可能形成初始访问的入口
- 与Web、代码审计专家协同构建完整攻击路径
"""
        return prompt


class CodeAuditorExpert(SecurityExpertAgent):
    """代码审计专家.

    专注于源代码审计、调用链分析、危险函数识别和数据流追踪。
    """

    ROLE_CONFIG_KEY = "code_auditor"

    def _build_task_prompt(self, task: str, context: dict[str, Any]) -> str:
        """构建代码审计专家任务提示词."""
        prompt = super()._build_task_prompt(task, context)
        prompt += """
额外要求：
- 重点关注：输入到危险点的数据流、高危漏洞模式、认证与授权代码、配置与部署
- 判断漏洞是否真实可利用
- 与Web/移动/网络Agent联动，将代码层结论转为实战突破判断
"""
        return prompt


class MobileSecurityExpert(SecurityExpertAgent):
    """移动安全专家.

    专注于Android/iOS应用安全、逆向工程、通信安全和客户端对抗分析。
    """

    ROLE_CONFIG_KEY = "mobile_security"

    def _build_task_prompt(self, task: str, context: dict[str, Any]) -> str:
        """构建移动安全专家任务提示词."""
        prompt = super()._build_task_prompt(task, context)
        prompt += """
额外要求：
- 重点关注：客户端逆向与保护、数据安全、通信安全、认证与授权、移动业务逻辑
- 判断问题是否只影响客户端，还是能延伸到服务端突破
- 与Web/代码审计/安全运营Agent联动，形成完整风险评估
"""
        return prompt


class SecurityOpsExpert(SecurityExpertAgent):
    """安全运营专家.

    专注于漏洞评估、事件分析、检测能力提升和响应方案制定。
    """

    ROLE_CONFIG_KEY = "security_ops"

    def _build_task_prompt(self, task: str, context: dict[str, Any]) -> str:
        """构建安全运营专家任务提示词."""
        prompt = super()._build_task_prompt(task, context)
        prompt += """
额外要求：
- 重点关注：漏洞风险评估、事件分析、检测与响应、云与容器安全、合规与治理
- 研判安全发现的业务影响和处置优先级
- 把其他Agent的发现整合成可运营、可落地的响应方案
"""
        return prompt

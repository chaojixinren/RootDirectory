"""记忆Agent（Memory）— 参考 memory.py 实现记忆压缩."""

from __future__ import annotations

from typing import Any

from backend.config.settings import get_settings
from backend.core.llm_client import LLMClient
from backend.models.agent import AgentConfig, AgentResult, AgentRole
from backend.models.memory import Clue, MemoryDigest, MemorySnapshot

from .base import BaseAgent


class MemoryAgent(BaseAgent):
    """记忆Agent — 负责维护和压缩执行历史.
    
    参考 memory.py 的设计，将较早轮次的历史压缩成结构化摘要。
    
    职责：
    1. 提取关键信息和线索
    2. 压缩较早的历史记录
    3. 维护滚动记忆摘要
    
    压缩触发条件：
    - 每N轮执行后
    - Token数超过阈值
    - 事件数超过阈值
    """

    # 默认配置（参考 memory.py）
    RECENT_ROUND_WINDOW = 1  # 保留最近1轮不压缩
    MAX_SECTION_ITEMS = 5    # 每个摘要部分最多5条
    DEFAULT_COMPRESS_INTERVAL = 3
    DEFAULT_EVENT_THRESHOLD = 24
    DEFAULT_TOKEN_THRESHOLD = 2000

    def __init__(
        self,
        config: AgentConfig | None = None,
        compress_interval: int = 3,
        event_threshold: int = 24,
        token_threshold: int = 2000,
        **kwargs: Any,
    ):
        if config is None:
            settings = get_settings()
            default_model = settings.llm.default_model or "gpt-4o"
            config = AgentConfig(
                role=AgentRole.MEMORY,
                name="记忆Agent",
                model=default_model,
                system_prompt=self._default_system_prompt(),
            )
        super().__init__(config, **kwargs)
        
        self.compress_interval = compress_interval
        self.event_threshold = event_threshold
        self.token_threshold = token_threshold

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是团队记忆压缩专家，负责把较早轮次的执行历史折叠成稳定、可复用的运行记忆。

你会拿到已有摘要和新增历史，请输出一个完整的新摘要，而不是增量 patch。

输出 JSON，格式如下：
{
  "mission_state": "一句话概括当前任务进展",
  "key_decisions": ["关键决策1"],
  "confirmed_findings": ["已确认发现1"],
  "failed_attempts": ["失败尝试或错误假设"],
  "open_questions": ["尚未解决的问题"],
  "next_focus": ["后续重点"]
}

要求：
1. 每个列表最多 5 条，避免重复。
2. 保留影响后续规划的内容：策略决策、确认发现、失败路径、未决问题。
3. 不要重复显而易见的代码结构或工具清单。
4. 输出必须是合法 JSON。
5. 保持信息密度，优先保留高价值信息。"""

    def should_compress(
        self,
        current_round: int,
        last_compressed_round: int,
        event_count: int,
        last_covered_event_count: int,
        estimated_tokens: int,
    ) -> bool:
        """判断是否需要压缩.
        
        参考 memory.py 的 should_compress 方法。
        
        Args:
            current_round: 当前轮次
            last_compressed_round: 上次压缩的轮次
            event_count: 当前事件数
            last_covered_event_count: 上次覆盖的事件数
            estimated_tokens: 估计的token数
            
        Returns:
            是否需要压缩
        """
        pending_rounds = current_round - last_compressed_round
        
        # 检查轮次间隔
        if pending_rounds >= self.compress_interval:
            return True
        
        # 检查事件数
        pending_events = event_count - last_covered_event_count
        if pending_events >= self.event_threshold:
            return True
        
        # 检查token数
        if estimated_tokens >= self.token_threshold:
            return True
        
        return False

    async def compress(
        self,
        goal: str,
        previous_digest: MemoryDigest | None,
        pending_rounds: list[dict[str, Any]],
        pending_clues: list[Clue],
    ) -> MemoryDigest:
        """执行记忆压缩.
        
        参考 memory.py 的 compress 方法。
        
        Args:
            goal: 任务目标
            previous_digest: 之前的记忆摘要
            pending_rounds: 待压缩的轮次
            pending_clues: 待处理的线索
            
        Returns:
            新的记忆摘要
        """
        # 构建压缩提示词
        prompt = self._build_compress_prompt(
            goal=goal,
            previous_digest=previous_digest,
            pending_rounds=pending_rounds,
            pending_clues=pending_clues,
        )
        
        try:
            # 调用LLM进行压缩
            response = await self.think_json(prompt)
            
            # 解析响应
            return self._parse_digest(
                response,
                covered_until_round=pending_rounds[-1].get("round_index", 0) if pending_rounds else 0,
                covered_event_count=len(pending_clues),
            )
        except Exception as exc:
            # 压缩失败，返回回退摘要
            return self._fallback_digest(
                pending_rounds=pending_rounds,
                previous_digest=previous_digest,
                covered_event_count=len(pending_clues),
                error=str(exc),
            )

    def _build_compress_prompt(
        self,
        goal: str,
        previous_digest: MemoryDigest | None,
        pending_rounds: list[dict[str, Any]],
        pending_clues: list[Clue],
    ) -> str:
        """构建压缩提示词."""
        prompt = f"""【任务目标】
{goal}

"""
        
        if previous_digest and not previous_digest.is_empty():
            prompt += f"【已有摘要】\n{previous_digest.to_prompt_text()}\n\n"
        
        # 添加待压缩的轮次
        prompt += "【新增执行历史】\n"
        for round_data in pending_rounds:
            prompt += f"\n轮次 {round_data.get('round_index', '?')}:\n"
            prompt += f"计划: {round_data.get('orchestrator_plan', '无')[:200]}...\n"
            
            for ar in round_data.get("agent_results", []):
                summary = ar.get("summary", '')[:100]
                prompt += f"- {ar.get('role', 'unknown')}: {summary}\n"
        
        # 添加线索
        if pending_clues:
            prompt += "\n【关键线索】\n"
            for clue in pending_clues[:10]:  # 最多10条
                prompt += f"- {clue.key} = {clue.value[:50]}\n"
        
        prompt += """
请基于以上信息，生成新的记忆摘要。

要求：
1. 保留关键决策和发现
2. 记录失败尝试，避免重复
3. 标记未决问题
4. 指出后续重点
"""
        
        return prompt

    def _parse_digest(
        self,
        response: dict[str, Any],
        covered_until_round: int,
        covered_event_count: int,
    ) -> MemoryDigest:
        """解析LLM响应为MemoryDigest."""
        return MemoryDigest(
            covered_until_round=covered_until_round,
            covered_event_count=covered_event_count,
            mission_state=response.get("mission_state", "")[:220],
            key_decisions=self._normalize_items(response.get("key_decisions", [])),
            confirmed_findings=self._normalize_items(response.get("confirmed_findings", [])),
            failed_attempts=self._normalize_items(response.get("failed_attempts", [])),
            open_questions=self._normalize_items(response.get("open_questions", [])),
            next_focus=self._normalize_items(response.get("next_focus", [])),
        )

    def _fallback_digest(
        self,
        pending_rounds: list[dict[str, Any]],
        previous_digest: MemoryDigest | None,
        covered_event_count: int,
        error: str,
    ) -> MemoryDigest:
        """压缩失败时的回退摘要."""
        # 提取新决策
        new_decisions = [
            r.get("coordinator_summary", "").strip()
            for r in pending_rounds
            if r.get("coordinator_summary", "").strip()
        ]
        
        # 提取失败尝试
        new_failures = [
            ar.get("summary", "").strip()
            for r in pending_rounds
            for ar in r.get("agent_results", [])
            if ar.get("status") == "failed" and ar.get("summary", "").strip()
        ]
        
        # 提取问题
        new_questions = [
            r.get("reflection_summary", "").strip()
            for r in pending_rounds
            if r.get("reflection_summary", "").strip()
        ]
        
        last_round = pending_rounds[-1] if pending_rounds else {}
        
        return MemoryDigest(
            covered_until_round=last_round.get("round_index", 0),
            covered_event_count=covered_event_count,
            mission_state=last_round.get("coordinator_summary", "")[:220]
            or (previous_digest.mission_state if previous_digest else "")
            or f"已完成 {len(pending_rounds)} 轮执行。",
            key_decisions=self._merge_items(
                previous_digest.key_decisions if previous_digest else [],
                new_decisions,
            ),
            confirmed_findings=previous_digest.confirmed_findings if previous_digest else [],
            failed_attempts=self._merge_items(
                previous_digest.failed_attempts if previous_digest else [],
                new_failures or [f"摘要压缩回退: {error[:120]}"],
            ),
            open_questions=self._merge_items(
                previous_digest.open_questions if previous_digest else [],
                new_questions,
            ),
            next_focus=self._merge_items(
                previous_digest.next_focus if previous_digest else [],
                [last_round.get("reflection_summary", "") or last_round.get("coordinator_summary", "")],
            ),
        )

    def _normalize_items(self, items: list[Any]) -> list[str]:
        """规范化列表项."""
        normalized = []
        for item in items:
            text = str(item)[:140]  # 截断到140字符
            if text and text not in normalized:
                normalized.append(text)
            if len(normalized) >= self.MAX_SECTION_ITEMS:
                break
        return normalized

    def _merge_items(self, old_items: list[str], new_items: list[str]) -> list[str]:
        """合并列表，去重并限制数量."""
        merged = []
        for item in old_items + new_items:
            text = str(item)[:140]
            if text and text not in merged:
                merged.append(text)
            if len(merged) >= self.MAX_SECTION_ITEMS:
                break
        return merged

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行记忆压缩（简化接口）."""
        context = context or {}
        
        digest = await self.compress(
            goal=task,
            previous_digest=context.get("previous_digest"),
            pending_rounds=context.get("pending_rounds", []),
            pending_clues=context.get("pending_clues", []),
        )
        
        return self.to_result(
            status="success",
            summary=f"记忆已更新，覆盖到第{digest.covered_until_round}轮",
            output=digest.to_prompt_text(),
        )

    def create_snapshot(
        self,
        task_id: str,
        round_index: int,
        digest: MemoryDigest,
        recent_clues: list[Clue],
        recent_rounds: list[dict[str, Any]],
    ) -> MemorySnapshot:
        """创建记忆快照."""
        return MemorySnapshot(
            task_id=task_id,
            round_index=round_index,
            digest=digest,
            recent_clues=recent_clues,
            recent_rounds=recent_rounds,
        )

"""BaseAgent抽象基类 — 所有Agent的基类."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Protocol

from backend.core.llm_client import LLMClient, LLMClientFactory
from backend.models.agent import AgentConfig, AgentMessage, AgentResult, AgentRole, AgentStatus
from backend.models.memory import Clue


class MessageHandler(Protocol):
    """消息处理器协议."""

    async def send_message(self, message: AgentMessage) -> None:
        """发送消息."""
        ...


class BaseAgent(ABC):
    """Agent抽象基类.
    
    所有Agent的基类，提供：
    - 配置管理
    - 步数控制
    - 状态管理
    - A2A消息发送
    """

    def __init__(
        self,
        config: AgentConfig,
        llm_client: LLMClient | None = None,
        message_handler: MessageHandler | None = None,
    ):
        self.config = config
        self.role = config.role
        self.agent_id = config.agent_id
        self.name = config.name
        self.llm = llm_client or LLMClientFactory.get_client()
        self.message_handler = message_handler
        
        # 执行状态
        self.status = AgentStatus.IDLE
        self.current_step = 0
        self.max_steps = config.max_steps
        self.current_task: str | None = None
        
        # 上下文
        self.context: dict[str, Any] = {}
        self.clues: list[Clue] = []
        self.messages: list[AgentMessage] = []

        # 执行追踪：捕获每次LLM调用的提示词和响应
        self._trace_records: list[dict[str, Any]] = []

    def _build_system_prompt(self) -> str:
        """构建系统提示词.
        
        子类可重写此方法添加自定义逻辑.
        """
        base_prompt = self.config.system_prompt
        
        # 如果有注入的Skills，添加到提示词
        if self.config.skills:
            skills_text = "\n\n【已激活的专业技能】\n"
            for skill in self.config.skills:
                skills_text += f"- {skill}\n"
            base_prompt += skills_text
        
        return base_prompt

    async def think(self, prompt: str, **kwargs: Any) -> str:
        """思考 — 调用LLM获取响应.
        
        这是Agent的核心思考方法.
        """
        import time
        system_prompt = self._build_system_prompt()
        
        start_time = time.time()
        response = await self.llm.complete_for_agent(
            agent_name=self.name,
            system_prompt=system_prompt,
            user_prompt=prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            **kwargs,
        )
        duration_ms = int((time.time() - start_time) * 1000)

        # 记录追踪信息
        self._trace_records.append({
            "system_prompt": system_prompt,
            "user_prompt": prompt,
            "llm_response": response,
            "model": self.config.model,
            "temperature": self.config.temperature,
            "duration_ms": duration_ms,
        })
        
        return response

    async def think_json(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """思考并返回JSON — 调用LLM并解析JSON响应."""
        response = await self.think(prompt, **kwargs)
        
        try:
            # 尝试提取JSON
            return self._extract_json(response)
        except ValueError as e:
            # 如果解析失败，返回结构化错误
            return {
                "error": f"JSON解析失败: {e}",
                "raw_response": response[:500],
                "status": "failed",
            }

    def _extract_json(self, text: str) -> dict[str, Any]:
        """从文本中提取JSON."""
        text = text.strip()
        
        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        
        # 尝试提取代码块中的JSON
        if "```json" in text:
            json_start = text.find("```json") + 7
            json_end = text.find("```", json_start)
            if json_end > json_start:
                try:
                    result = json.loads(text[json_start:json_end].strip())
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass
        
        # 尝试提取 ``` 中的内容
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                try:
                    result = json.loads(part.strip())
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    continue
        
        # 尝试提取花括号中的JSON
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                result = json.loads(text[start : end + 1])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法提取有效JSON: {text[:200]}...")

    async def send_message(
        self,
        to_agent: str,
        msg_type: str,
        payload: dict[str, Any],
        natural_language: str | None = None,
    ) -> None:
        """发送A2A消息."""
        message = AgentMessage(
            from_agent=self.agent_id,
            to_agent=to_agent,
            msg_type=msg_type,
            payload=payload,
            natural_language=natural_language,
        )
        
        self.messages.append(message)
        
        if self.message_handler:
            await self.message_handler.send_message(message)

    def check_step_limit(self) -> bool:
        """检查是否达到步数限制.
        
        Returns:
            True: 未达到限制，可以继续
            False: 已达到限制
        """
        return self.current_step < self.max_steps

    def increment_step(self) -> None:
        """增加步数计数."""
        self.current_step += 1

    def reset_step(self) -> None:
        """重置步数计数."""
        self.current_step = 0

    def add_clue(self, key: str, value: str, confidence: float = 1.0) -> Clue:
        """添加线索."""
        clue = Clue(
            key=key,
            value=value,
            source_agent=self.agent_id,
            confidence=confidence,
        )
        self.clues.append(clue)
        return clue

    def get_clues_by_key(self, key: str) -> list[Clue]:
        """获取指定key的线索."""
        return [c for c in self.clues if c.key == key]

    @abstractmethod
    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行任务.
        
        子类必须实现此方法.
        
        Args:
            task: 任务描述
            context: 执行上下文
            
        Returns:
            Agent执行结果
        """
        pass

    def to_result(self, status: str, summary: str, output: str = "") -> AgentResult:
        """生成执行结果."""
        return AgentResult(
            agent_id=self.agent_id,
            role=self.role,
            status=status,
            summary=summary,
            output=output,
            clues=[{"key": c.key, "value": c.value, "confidence": c.confidence} for c in self.clues],
        )

    def reset(self) -> None:
        """重置Agent状态."""
        self.status = AgentStatus.IDLE
        self.current_step = 0
        self.current_task = None
        self.context = {}
        self.clues = []
        self.messages = []
        self._trace_records = []

    def get_and_clear_traces(self) -> list[dict[str, Any]]:
        """获取并清空追踪记录."""
        traces = self._trace_records.copy()
        self._trace_records = []
        return traces


class ReActAgent(BaseAgent):
    """ReAct模式Agent基类.
    
    实现ReAct循环：
    Thought -> Action -> Observation -> ... -> Answer
    """

    def __init__(
        self,
        config: AgentConfig,
        llm_client: LLMClient | None = None,
        message_handler: MessageHandler | None = None,
    ):
        super().__init__(config, llm_client, message_handler)
        self.observations: list[str] = []
        self.actions: list[dict[str, Any]] = []

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """执行ReAct循环."""
        self.reset()
        self.current_task = task
        self.status = AgentStatus.RUNNING
        
        if context:
            self.context.update(context)
        
        try:
            while self.check_step_limit():
                self.increment_step()
                
                # 思考步骤
                thought = await self._think_step()
                
                # 检查是否完成任务
                if self._is_complete(thought):
                    return self._complete(thought)
                
                # 执行动作
                action_result = await self._act_step(thought)
                
                # 观察结果
                observation = await self._observe_step(action_result)
                self.observations.append(observation)
                
                # 检查是否需要反思
                if self._should_reflect():
                    await self._reflect()
            
            # 达到步数限制
            return self.to_result(
                status="partial",
                summary=f"达到最大步数限制({self.max_steps})",
                output="\n".join(self.observations),
            )
            
        except Exception as e:
            self.status = AgentStatus.FAILED
            return self.to_result(
                status="failed",
                summary=f"执行异常: {e}",
                output="\n".join(self.observations),
            )

    @abstractmethod
    async def _think_step(self) -> dict[str, Any]:
        """思考步骤.
        
        分析当前情况，决定下一步动作.
        
        Returns:
            思考结果，包含thought和可能的action
        """
        pass

    @abstractmethod
    async def _act_step(self, thought: dict[str, Any]) -> dict[str, Any]:
        """执行动作步骤.
        
        根据思考结果执行具体动作.
        
        Args:
            thought: 思考结果
            
        Returns:
            动作执行结果
        """
        pass

    @abstractmethod
    async def _observe_step(self, action_result: dict[str, Any]) -> str:
        """观察步骤.
        
        观察动作执行的结果.
        
        Args:
            action_result: 动作执行结果
            
        Returns:
            观察描述
        """
        pass

    def _is_complete(self, thought: dict[str, Any]) -> bool:
        """检查是否完成任务.
        
        子类可重写此方法.
        """
        return thought.get("is_complete", False) or thought.get("status") == "completed"

    def _complete(self, thought: dict[str, Any]) -> AgentResult:
        """完成任务."""
        self.status = AgentStatus.COMPLETED
        return self.to_result(
            status="success",
            summary=thought.get("summary", "任务完成"),
            output=thought.get("output", ""),
        )

    def _should_reflect(self) -> bool:
        """检查是否需要反思.
        
        子类可重写此方法.
        """
        return False

    async def _reflect(self) -> None:
        """执行反思.
        
        子类可重写此方法.
        """
        pass

    def reset(self) -> None:
        """重置ReAct状态."""
        super().reset()
        self.observations = []
        self.actions = []

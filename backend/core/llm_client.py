"""LLM客户端封装 — OpenAI兼容接口."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from openai import AsyncOpenAI, APITimeoutError, APIConnectionError, OpenAIError
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from backend.config.settings import get_settings


class LLMResponse:
    """LLM响应封装."""

    def __init__(
        self,
        content: str,
        model: str,
        usage: dict[str, int] | None = None,
        raw_response: Any | None = None,
    ):
        self.content = content
        self.model = model
        self.usage = usage or {}
        self.raw_response = raw_response

    def __repr__(self) -> str:
        return f"LLMResponse(model={self.model}, content_len={len(self.content)})"

    def extract_json(self) -> dict[str, Any]:
        """从响应中提取JSON."""
        text = self.content.strip()
        
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取代码块中的JSON
        if "```json" in text:
            json_start = text.find("```json") + 7
            json_end = text.find("```", json_start)
            if json_end > json_start:
                try:
                    return json.loads(text[json_start:json_end].strip())
                except json.JSONDecodeError:
                    pass
        
        # 尝试提取花括号中的JSON
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法从响应中提取有效JSON: {text[:200]}...")


class LLMClient(ABC):
    """LLM客户端抽象基类."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """非流式完成请求."""
        pass

    @abstractmethod
    async def complete_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式完成请求."""
        pass

    async def complete_for_agent(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> str:
        """为Agent完成请求（简化接口）.
        
        参考 memory.py 中的调用方式.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        response = await self.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content


class OpenAIClient(LLMClient):
    """OpenAI兼容客户端."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        super().__init__(api_key, base_url, default_model, timeout, max_retries)
        
        # 加载配置
        settings = get_settings()
        self.api_key = api_key or settings.llm.api_key
        self.base_url = base_url or settings.llm.base_url
        self.default_model = default_model or settings.llm.default_model
        
        # 检测是否为百度千帆Coding API (Key包含ALTAKSP-)
        self.is_qianfan_coding = "qianfan" in self.base_url.lower() and "ALTAKSP-" in self.api_key
        
        # 初始化客户端
        # 对于Coding API，需要使用 /v2/coding 路径
        client_base_url = self.base_url
        if self.is_qianfan_coding and not self.base_url.endswith("/coding"):
            client_base_url = self.base_url.rstrip("/") + "/coding"
        
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=client_base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """非流式完成请求（含超时重试）."""
        import asyncio
        model = model or self.default_model
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response: ChatCompletion = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
                
                content = response.choices[0].message.content or ""
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                }
                
                return LLMResponse(
                    content=content,
                    model=response.model,
                    usage=usage,
                    raw_response=response,
                )
            except (APITimeoutError, APIConnectionError) as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = min(2 ** (attempt + 1), 30)
                    print(f"[LLM] 请求超时/连接失败 (尝试 {attempt+1}/{self.max_retries+1}): {e}, {wait}s 后重试...")
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"LLM请求失败 (已重试{self.max_retries}次): {e}") from e
            except OpenAIError as e:
                raise RuntimeError(f"LLM请求失败: {e}") from e
        raise RuntimeError(f"LLM请求失败: {last_error}") from last_error

    async def complete_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式完成请求."""
        model = model or self.default_model
        
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs,
            )
            
            async for chunk in stream:
                chunk: ChatCompletionChunk
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except OpenAIError as e:
            raise RuntimeError(f"LLM流式请求失败: {e}") from e


class LLMClientFactory:
    """LLM客户端工厂."""

    _instances: dict[str, LLMClient] = {}

    @classmethod
    def get_client(
        cls,
        provider: str = "openai",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> LLMClient:
        """获取或创建客户端实例."""
        cache_key = f"{provider}:{base_url or 'default'}"
        
        if cache_key not in cls._instances:
            if provider == "openai":
                cls._instances[cache_key] = OpenAIClient(
                    api_key=api_key,
                    base_url=base_url,
                )
            else:
                raise ValueError(f"不支持的LLM提供商: {provider}")
        
        return cls._instances[cache_key]

    @classmethod
    def clear_cache(cls) -> None:
        """清除缓存."""
        cls._instances.clear()


# 便捷函数
async def complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> LLMResponse:
    """便捷完成函数."""
    client = LLMClientFactory.get_client()
    return await client.complete(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def complete_for_agent(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4000,
) -> str:
    """便捷Agent完成函数."""
    client = LLMClientFactory.get_client()
    return await client.complete_for_agent(
        agent_name="default",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

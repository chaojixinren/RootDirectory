"""配置管理系统 — 统一管理所有配置."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """LLM配置."""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(default="", description="API密钥")
    base_url: str = Field(default="https://api.openai.com/v1", description="API基础URL")
    default_model: str = Field(default="gpt-4o", description="默认模型")
    default_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    default_max_tokens: int = Field(default=4000, ge=100, le=32000)
    timeout: int = Field(default=180, description="请求超时(秒)")
    max_retries: int = Field(default=3, description="最大重试次数")


class AgentDefaults(BaseSettings):
    """Agent默认配置."""

    model_config = SettingsConfigDict(env_prefix="AGENT_")

    orchestrator_model: str = Field(default="gpt-4o")
    orchestrator_max_steps: int = Field(default=10)

    thinker_model: str = Field(default="gpt-4o")
    thinker_max_steps: int = Field(default=15)

    executor_model: str = Field(default="gpt-4o-mini")
    executor_max_steps: int = Field(default=20)

    reflector_model: str = Field(default="gpt-4o")
    reflector_interval: int = Field(default=3, description="反思间隔(轮)")

    memory_model: str = Field(default="gpt-4o-mini")
    compress_interval: int = Field(default=3, description="压缩间隔(轮)")
    token_threshold: int = Field(default=2000, description="Token阈值")


class WorkflowConfig(BaseSettings):
    """工作流配置."""

    model_config = SettingsConfigDict(env_prefix="WORKFLOW_")

    max_rounds: int = Field(default=20, description="最大执行轮数")
    stall_threshold: int = Field(default=3, description="停滞检测阈值(轮无进展则触发反思)")
    enable_parallel: bool = Field(default=True, description="是否启用并行执行")
    max_parallel_agents: int = Field(default=5, description="最大并行Agent数")


class ServerConfig(BaseSettings):
    """服务器配置."""

    model_config = SettingsConfigDict(env_prefix="SERVER_")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    workers: int = Field(default=1)
    reload: bool = Field(default=False, description="开发模式热重载")
    log_level: str = Field(default="info")


class Settings(BaseSettings):
    """全局配置类."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 项目根目录
    project_root: Path = Field(default=Path(__file__).parent.parent.parent)

    # 子配置
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent_defaults: AgentDefaults = Field(default_factory=AgentDefaults)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    # 路径配置
    skills_dir: Path = Field(default=Path("skills"))
    prompts_dir: Path = Field(default=Path("prompts"))
    config_dir: Path = Field(default=Path("config"))

    # 调试配置
    debug: bool = Field(default=False)
    verbose: bool = Field(default=False)

    @field_validator("skills_dir", "prompts_dir", "config_dir")
    @classmethod
    def resolve_path(cls, v: Path, info) -> Path:
        """解析相对路径为绝对路径."""
        if not v.is_absolute():
            # 从项目根目录解析
            values = info.data
            root = values.get("project_root", Path.cwd())
            return root / v
        return v

    def load_yaml_config(self, filename: str) -> dict[str, Any]:
        """加载YAML配置文件."""
        path = self.config_dir / filename
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def save_yaml_config(self, filename: str, data: dict[str, Any]) -> None:
        """保存YAML配置文件."""
        path = self.config_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)


# 全局配置实例
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置（单例）."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """重新加载配置."""
    global _settings
    _settings = Settings()
    return _settings

"""配置管理器 — 运行时配置热重载."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.config.settings import get_settings


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变更处理器."""

    def __init__(self, manager: ConfigManager) -> None:
        self.manager = manager

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        if event.src_path.endswith((".yaml", ".yml")):
            self.manager.reload_if_changed(event.src_path)


class ConfigManager:
    """配置管理器 — 支持热重载."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.settings = get_settings()
        self.config_dir = config_dir or self.settings.config_dir
        self._cache: dict[str, dict[str, Any]] = {}
        self._observer: Observer | None = None
        self._setup_watcher()

    def _setup_watcher(self) -> None:
        """设置文件监控."""
        if not self.config_dir.exists():
            return

        handler = ConfigFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.config_dir), recursive=False)
        self._observer.start()

    def stop_watcher(self) -> None:
        """停止文件监控."""
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def load(self, filename: str) -> dict[str, Any]:
        """加载配置文件（带缓存）."""
        if filename not in self._cache:
            self._cache[filename] = self._load_file(filename)
        return self._cache[filename]

    def load_yaml_config(self, filename: str) -> dict[str, Any]:
        """加载YAML配置文件（兼容方法）."""
        return self.load(filename)

    def _load_file(self, filename: str) -> dict[str, Any]:
        """加载配置文件."""
        path = self.config_dir / filename
        if not path.exists():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def reload_if_changed(self, filepath: str) -> None:
        """文件变更时重载."""
        path = Path(filepath)
        filename = path.name
        if filename in self._cache:
            self._cache[filename] = self._load_file(filename)
            print(f"[ConfigManager] 配置已重载: {filename}")

    def get_agent_config(self, agent_role: str) -> dict[str, Any]:
        """获取Agent配置."""
        configs = self.load("agents.yaml")
        return configs.get(agent_role, {})

    def get_skill_categories(self) -> dict[str, Any]:
        """获取Skills分类配置."""
        return self.load("skills.yaml")

    def update_agent_prompt(self, agent_role: str, prompt: str) -> None:
        """更新Agent提示词."""
        configs = self.load("agents.yaml")
        if agent_role in configs:
            configs[agent_role]["system_prompt"] = prompt
            self.save("agents.yaml", configs)

    def save(self, filename: str, data: dict[str, Any]) -> None:
        """保存配置文件."""
        path = self.config_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)

        # 更新缓存
        self._cache[filename] = data


# 全局实例
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """获取配置管理器（单例）."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

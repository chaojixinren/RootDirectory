"""Skills加载器 — 动态加载和热重载."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.models.skill import SkillDefinition
from backend.skills.manager import SkillManager


class SkillsFileHandler(FileSystemEventHandler):
    """Skills文件变更处理器."""

    def __init__(self, loader: SkillLoader):
        self.loader = loader

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        if event.src_path.endswith(".yaml"):
            self.loader.reload_file(event.src_path)

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        if event.src_path.endswith(".yaml"):
            self.loader.reload_file(event.src_path)

    def on_deleted(self, event) -> None:
        if event.is_directory:
            return
        if event.src_path.endswith(".yaml"):
            self.loader.remove_file(event.src_path)


class SkillLoader:
    """Skills加载器.
    
    支持动态加载和热重载。
    """

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self._observer: Observer | None = None
        self._last_reload: dict[str, float] = {}

    def start_watching(self) -> None:
        """开始监听文件变更."""
        if not self.manager.skills_dir.exists():
            return
        
        handler = SkillsFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.manager.skills_dir), recursive=True)
        self._observer.start()

    def stop_watching(self) -> None:
        """停止监听."""
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def reload_file(self, filepath: str) -> None:
        """重载单个文件."""
        # 防抖：避免短时间内重复加载
        now = time.time()
        last = self._last_reload.get(filepath, 0)
        if now - last < 1.0:
            return
        
        self._last_reload[filepath] = now
        
        # 加载文件
        path = Path(filepath)
        skill = self.manager._load_skill_file(path)
        
        if skill:
            self.manager._skills[skill.full_name] = skill
            self.manager._rebuild_tree()
            print(f"[SkillLoader] Skill已重载: {skill.full_name}")

    def remove_file(self, filepath: str) -> None:
        """移除文件对应的Skill."""
        path = Path(filepath)
        rel_path = path.relative_to(self.manager.skills_dir)
        category = "/".join(rel_path.parent.parts)
        name = path.stem
        full_name = f"{category}/{name}"
        
        if full_name in self.manager._skills:
            del self.manager._skills[full_name]
            self.manager._rebuild_tree()
            print(f"[SkillLoader] Skill已移除: {full_name}")

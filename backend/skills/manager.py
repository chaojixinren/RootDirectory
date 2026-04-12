"""Skills管理器 — 树状分类管理."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.models.skill import SkillDefinition, SkillNode


class SkillManager:
    """Skills管理器.
    
    管理树状分类的Skills，支持动态加载和检索。
    """

    def __init__(self, skills_dir: str | Path | None = None):
        self.skills_dir = Path(skills_dir) if skills_dir else Path("skills")
        self._skills: dict[str, SkillDefinition] = {}
        self._tree: SkillNode | None = None

    def load_all(self) -> int:
        """加载所有Skills.
        
        Returns:
            加载的Skills数量
        """
        if not self.skills_dir.exists():
            return 0
        
        count = 0
        for skill_file in self.skills_dir.rglob("*.yaml"):
            skill = self._load_skill_file(skill_file)
            if skill:
                self._skills[skill.full_name] = skill
                count += 1
        
        # 重建树
        self._rebuild_tree()
        
        return count

    def _load_skill_file(self, path: Path) -> SkillDefinition | None:
        """加载单个Skill文件."""
        try:
            import yaml
            
            content = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not content:
                return None
            
            # 计算分类路径
            rel_path = path.relative_to(self.skills_dir)
            category = "/".join(rel_path.parent.parts)
            
            return SkillDefinition(
                name=path.stem,
                category=category,
                description=content.get("description", ""),
                when_to_use=content.get("when_to_use", ""),
                content=content.get("content", ""),
                tags=content.get("tags", []),
                priority=content.get("priority", 0),
                version=content.get("version", "1.0"),
                author=content.get("author", ""),
            )
            
        except Exception as e:
            print(f"加载Skill失败 {path}: {e}")
            return None

    def _rebuild_tree(self) -> None:
        """重建Skills树."""
        root = SkillNode(name="root", path="", is_category=True)
        
        for skill in self._skills.values():
            self._add_to_tree(root, skill)
        
        self._tree = root

    def _add_to_tree(self, root: SkillNode, skill: SkillDefinition) -> None:
        """将Skill添加到树中."""
        parts = skill.category_parts
        current = root
        
        # 创建或找到分类节点
        for part in parts:
            if not part:
                continue
            
            path = f"{current.path}/{part}" if current.path else part
            
            # 查找现有节点
            child = next((c for c in current.children if c.name == part), None)
            
            if child is None:
                child = SkillNode(
                    name=part,
                    path=path,
                    is_category=True,
                )
                current.children.append(child)
            
            current = child
        
        # 添加Skill节点
        skill_node = SkillNode(
            name=skill.name,
            path=skill.full_name,
            is_category=False,
            skill=skill,
        )
        current.children.append(skill_node)

    def get_skill(self, full_name: str) -> SkillDefinition | None:
        """获取Skill."""
        return self._skills.get(full_name)

    def get_by_category(self, category: str) -> list[SkillDefinition]:
        """获取分类下的所有Skills."""
        return [
            s for s in self._skills.values()
            if s.category == category or s.category.startswith(f"{category}/")
        ]

    def search(self, query: str) -> list[SkillDefinition]:
        """搜索Skills."""
        query_lower = query.lower()
        results = []
        
        for skill in self._skills.values():
            score = 0
            
            # 名称匹配
            if query_lower in skill.name.lower():
                score += 10
            
            # 分类匹配
            if query_lower in skill.category.lower():
                score += 5
            
            # 描述匹配
            if skill.description and query_lower in skill.description.lower():
                score += 3
            
            # 标签匹配
            if any(query_lower in tag.lower() for tag in skill.tags):
                score += 8
            
            if score > 0:
                results.append((skill, score))
        
        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in results]

    def get_tree(self) -> SkillNode | None:
        """获取Skills树."""
        return self._tree

    def list_all(self) -> list[SkillDefinition]:
        """列出所有Skills."""
        return list(self._skills.values())

    def save_skill(self, skill: SkillDefinition) -> None:
        """保存Skill到文件."""
        import yaml
        
        # 构建文件路径
        category_path = "/".join(skill.category_parts)
        skill_dir = self.skills_dir / category_path
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        skill_file = skill_dir / f"{skill.name}.yaml"
        
        # 保存
        data = {
            "description": skill.description,
            "when_to_use": skill.when_to_use,
            "content": skill.content,
            "tags": skill.tags,
            "priority": skill.priority,
            "version": skill.version,
            "author": skill.author,
        }
        
        skill_file.write_text(
            yaml.dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        
        # 更新内存
        self._skills[skill.full_name] = skill
        self._rebuild_tree()

    def delete_skill(self, full_name: str) -> bool:
        """删除Skill."""
        skill = self._skills.get(full_name)
        if not skill:
            return False
        
        # 删除文件
        skill_file = self.skills_dir / f"{skill.category}/{skill.name}.yaml"
        if skill_file.exists():
            skill_file.unlink()
        
        # 更新内存
        del self._skills[full_name]
        self._rebuild_tree()
        
        return True

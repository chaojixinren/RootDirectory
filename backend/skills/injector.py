"""Skills注入器 — 根据场景自动注入Skills."""

from __future__ import annotations

import re
from typing import Any

from backend.models.skill import SkillDefinition, SkillInjection, SkillMatch
from backend.skills.manager import SkillManager


class SkillInjector:
    """Skills注入器.
    
    根据任务场景自动匹配和注入相关Skills。
    """

    def __init__(self, manager: SkillManager):
        self.manager = manager

    async def detect_and_inject(
        self,
        task: str,
        agent_role: str,
        task_id: str,
        agent_id: str,
        top_k: int = 3,
    ) -> SkillInjection:
        """检测场景并注入Skills.
        
        Args:
            task: 任务描述
            agent_role: Agent角色
            task_id: 任务ID
            agent_id: Agent ID
            top_k: 最多注入的Skills数量
            
        Returns:
            注入记录
        """
        # 匹配Skills
        matches = await self.match_skills(task, agent_role)
        
        # 选择top_k
        selected = matches[:top_k]
        skills = [m.skill for m in selected]
        
        # 构建注入上下文
        context = self._build_context(skills)
        
        return SkillInjection(
            task_id=task_id,
            agent_id=agent_id,
            skills=skills,
            context=context,
        )

    async def match_skills(
        self,
        task: str,
        agent_role: str,
    ) -> list[SkillMatch]:
        """匹配Skills.
        
        使用多种策略匹配：
        1. 关键词匹配
        2. 分类匹配
        3. 标签匹配
        4. 使用场景匹配
        """
        matches = []
        task_lower = task.lower()
        
        for skill in self.manager.list_all():
            score = 0
            reasons = []
            
            # 关键词匹配（名称和描述）
            if skill.name.lower() in task_lower:
                score += 15
                reasons.append(f"名称匹配: {skill.name}")
            
            if skill.description and any(
                word in task_lower 
                for word in skill.description.lower().split()[:5]
            ):
                score += 5
                reasons.append("描述关键词匹配")
            
            # 分类匹配
            category_parts = skill.category_parts
            for part in category_parts:
                if part.lower() in task_lower:
                    score += 8
                    reasons.append(f"分类匹配: {part}")
            
            # 标签匹配
            for tag in skill.tags:
                if tag.lower() in task_lower:
                    score += 10
                    reasons.append(f"标签匹配: {tag}")
            
            # 使用场景匹配
            if skill.when_to_use:
                # 提取场景中的关键词
                scene_words = re.findall(r"\w+", skill.when_to_use.lower())
                matches_count = sum(1 for word in scene_words if word in task_lower)
                if matches_count > 0:
                    score += matches_count * 3
                    reasons.append("使用场景匹配")
            
            # 角色匹配：某些Skill更适合特定角色
            if agent_role == "executor" and "pentest" in skill.category:
                score += 5  # 执行Agent更适合渗透测试任务
            
            if agent_role == "thinker" and "coding" in skill.category:
                score += 5  # 思考专家更适合代码相关任务
            
            # 优先级加成
            score += skill.priority * 0.5
            
            if score > 5:  # 最小阈值
                matches.append(SkillMatch(
                    skill=skill,
                    score=score,
                    reason="; ".join(reasons[:2]),
                ))
        
        # 按分数排序
        matches.sort(key=lambda x: x.score, reverse=True)
        
        return matches

    def _build_context(self, skills: list[SkillDefinition]) -> str:
        """构建注入上下文."""
        if not skills:
            return ""
        
        parts = ["【已激活的专业技能】\n"]
        
        for skill in skills:
            parts.append(f"\n### {skill.name} ({skill.category})")
            parts.append(f"{skill.description}\n")
            
            if skill.when_to_use:
                parts.append(f"**使用场景**: {skill.when_to_use}\n")
            
            if skill.content:
                # 只取内容的前500字符，避免prompt过长
                content = skill.content[:500]
                if len(skill.content) > 500:
                    content += "\n... (内容已截断)"
                parts.append(content)
            
            parts.append("")
        
        return "\n".join(parts)

    def format_for_prompt(self, injection: SkillInjection) -> str:
        """格式化为Prompt文本."""
        return injection.context

    def quick_match(
        self,
        keywords: list[str],
        category_prefix: str | None = None,
    ) -> list[SkillDefinition]:
        """快速匹配 — 根据关键词列表快速查找."""
        results = []
        
        for skill in self.manager.list_all():
            # 分类过滤
            if category_prefix and not skill.category.startswith(category_prefix):
                continue
            
            # 关键词匹配
            skill_text = f"{skill.name} {skill.description} {' '.join(skill.tags)}".lower()
            match_count = sum(1 for kw in keywords if kw.lower() in skill_text)
            
            if match_count >= len(keywords) / 2:  # 至少匹配一半
                results.append(skill)
        
        return results[:5]  # 最多返回5个

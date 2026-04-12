"""LangGraph边定义 — 条件路由."""

from __future__ import annotations

from backend.models.state import GraphState


# 安全专家角色列表
SECURITY_EXPERT_ROLES = [
    "web_security",
    "network_penetration",
    "code_auditor",
    "mobile_security",
    "security_ops",
]


class ConditionalEdges:
    """条件边定义.

    定义工作流中的条件路由逻辑。
    """

    @staticmethod
    def should_continue(state: GraphState) -> str:
        """检查是否应该继续执行.

        Returns:
            "continue": 继续下一轮
            "finalize": 结束执行
            "reflect": 触发反思
        """
        # 检查是否已完成
        if state.is_completed:
            return "finalize"

        # 检查是否达到最大轮数
        if state.current_round >= state.max_rounds:
            return "finalize"

        # 检查是否应该继续
        if not state.should_continue:
            return "finalize"

        # 检查是否停滞
        if state.is_stalled:
            return "reflect"

        return "continue"

    @staticmethod
    def route_after_reflection(state: GraphState) -> str:
        """反思后的路由.

        Returns:
            "continue": 继续执行，使用新策略
            "finalize": 反思建议终止
        """
        # 检查是否已完成
        if state.is_completed:
            return "finalize"

        # 检查是否达到最大轮数
        if state.current_round >= state.max_rounds:
            return "finalize"

        # 检查是否应该继续
        if not state.should_continue:
            return "finalize"

        # 如果反思后仍然停滞且轮数接近上限，终止
        if state.is_stalled and state.current_round >= state.max_rounds - 2:
            return "finalize"

        return "continue"

    @staticmethod
    def dispatch_sub_tasks(state: GraphState) -> list[str]:
        """分发子任务.

        根据orchestrator分配的子任务，决定调用哪些专家Agent。

        Returns:
            要执行的Agent节点列表
        """
        # 安全检查：超出最大轮数时直接终止
        if state.is_completed or state.current_round >= state.max_rounds:
            return ["finalize"]

        nodes = []

        for task in state.sub_tasks:
            role = task.get("agent_role")
            status = task.get("status", "pending")

            if status == "pending":
                # 安全专家
                if role in SECURITY_EXPERT_ROLES:
                    nodes.append(role)
                # 传统Agent（向后兼容）
                elif role == "thinker":
                    nodes.append("thinker")
                elif role == "executor":
                    nodes.append("executor")

        # 去重
        return list(set(nodes)) if nodes else ["finalize"]

    @staticmethod
    def dispatch_security_experts(state: GraphState) -> list[str]:
        """分发安全专家任务（专门用于安全测试场景）.

        Orchestrator分析任务后，决定调用哪些安全专家。

        Returns:
            要执行的安全专家节点列表
        """
        nodes = []

        for task in state.sub_tasks:
            role = task.get("agent_role")
            status = task.get("status", "pending")

            if status == "pending" and role in SECURITY_EXPERT_ROLES:
                nodes.append(role)

        return list(set(nodes)) if nodes else ["finalize"]

    @staticmethod
    def should_compress_memory(state: GraphState) -> str:
        """检查是否应该压缩记忆.

        Returns:
            "compress": 需要压缩
            "skip": 跳过压缩
        """
        # 检查当前轮次
        if state.current_round % 3 == 0 and state.current_round > 0:
            return "compress"

        # 检查线索数量
        if len(state.recent_clues) >= 20:
            return "compress"

        return "skip"

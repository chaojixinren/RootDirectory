"""LangGraph工作流定义 — 主工作流构建.

新的多Agent安全专家工作流：

                              ┌─────────────┐
                              │    START    │
                              └──────┬──────┘
                                     ▼
                         ┌───────────────────────┐
                         │    orchestrator       │◄──────────────────────────┐
                         │  (协调指挥官)          │                           │
                         │  分析任务、调度专家    │                           │
                         └───────────┬───────────┘                           │
                                     ▼                                       │
                  ┌──────────────────────────────────┐                      │
                  │  dispatch_security_experts       │                      │
                  │  (安全专家并行调度)               │                      │
                  └──────────────────────────────────┘                      │
                          │    │    │    │    │                             │
             ┌────────────┘    │    │    │    └────────────┐                │
             ▼                 ▼    ▼    ▼                 ▼                │
    ┌─────────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────┐      │
    │   web_security  │ │ network  │ │  code    │ │ mobile_security │      │
    │  (Web安全专家)   │ │_penetration│ │_auditor  │  (移动安全专家)   │      │
    └────────┬────────┘ └────┬─────┘ └────┬─────┘ └────────┬────────┘      │
             │               │            │                │               │
             │         ┌─────┴────────────┴─────┐          │               │
             │         ▼                        ▼          │               │
             │  ┌──────────────┐          ┌──────────────┐  │               │
             │  │ security_ops │          │  parallel_join│  │               │
             │  │ (安全运营专家)│          │  (结果汇聚)    │  │               │
             │  └──────┬───────┘          └───────┬──────┘  │               │
             │         └──────────────────────────┘          │               │
             └──────────────────┬────────────────────────────┘               │
                                ▼                                            │
                    ┌────────────────────┐                                   │
                    │    reflector       │                                   │
                    │  (反思专家-评估质量) │                                   │
                    └──────────┬─────────┘                                   │
                               ▼                                            │
                 ┌──────────────────────────────┐                          │
                 │  should_continue (继续检查)   │                          │
                 └──────────────┬───────────────┘                          │
                                │                                          │
              ┌─────────────────┼─────────────────┐                         │
              ▼                 ▼                 ▼                         │
        ┌─────────┐   ┌────────────────┐   ┌──────────┐                    │
        │finalize │   │   memory       │   │ continue │────────────────────┘
        │ (结束)  │   │ (记忆压缩)      │   │ (下一轮) │
        └────┬────┘   └────────────────┘   └──────────┘
             │
             ▼
        ┌─────────┐
        │   END   │
        └─────────┘
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.core.llm_client import LLMClient
from backend.models.state import GraphState

from .edges import ConditionalEdges, SECURITY_EXPERT_ROLES
from .nodes import AgentNodes


def build_workflow(llm_client: LLMClient | None = None) -> CompiledStateGraph:
    """构建主工作流图 — 支持多Agent安全专家协作.

    工作流特点：
    1. Orchestrator分析任务并决定调用哪些安全专家
    2. 多个安全专家可以并行执行
    3. Reflector评估所有专家输出质量
    4. Orchestrator基于所有输出做最终决策
    5. 支持多轮迭代直到任务完成

    Args:
        llm_client: LLM客户端

    Returns:
        编译后的状态图
    """
    # 创建节点集合
    nodes = AgentNodes(llm_client)

    # 创建工作流
    workflow = StateGraph(GraphState)

    # ============ 添加节点 ============

    # 核心节点
    workflow.add_node("orchestrator", nodes.orchestrator_node)
    workflow.add_node("parallel_join", _parallel_join_node)
    workflow.add_node("memory", nodes.memory_node)
    workflow.add_node("reflector", nodes.reflector_node)
    workflow.add_node("finalize", nodes.finalize_node)

    # 安全专家节点
    workflow.add_node("web_security", nodes.web_security_node)
    workflow.add_node("network_penetration", nodes.network_penetration_node)
    workflow.add_node("code_auditor", nodes.code_auditor_node)
    workflow.add_node("mobile_security", nodes.mobile_security_node)
    workflow.add_node("security_ops", nodes.security_ops_node)

    # 传统Agent节点（向后兼容）
    workflow.add_node("thinker", nodes.thinker_node)
    workflow.add_node("executor", nodes.executor_node)

    # ============ 定义边 ============

    # START -> orchestrator
    workflow.add_edge(START, "orchestrator")

    # orchestrator -> 任务分发（并行执行多个安全专家）
    workflow.add_conditional_edges(
        "orchestrator",
        ConditionalEdges.dispatch_sub_tasks,
        {
            # 安全专家
            "web_security": "web_security",
            "network_penetration": "network_penetration",
            "code_auditor": "code_auditor",
            "mobile_security": "mobile_security",
            "security_ops": "security_ops",
            # 传统Agent（向后兼容）
            "thinker": "thinker",
            "executor": "executor",
            # 结束
            "finalize": "finalize",
        },
    )

    # 所有专家节点 -> parallel_join（汇聚结果）
    workflow.add_edge("web_security", "parallel_join")
    workflow.add_edge("network_penetration", "parallel_join")
    workflow.add_edge("code_auditor", "parallel_join")
    workflow.add_edge("mobile_security", "parallel_join")
    workflow.add_edge("security_ops", "parallel_join")
    workflow.add_edge("thinker", "parallel_join")
    workflow.add_edge("executor", "parallel_join")

    # parallel_join -> reflector（反思专家评估所有输出）
    workflow.add_edge("parallel_join", "reflector")

    # reflector -> 反思后路由
    workflow.add_conditional_edges(
        "reflector",
        ConditionalEdges.route_after_reflection,
        {
            "continue": "orchestrator",  # 继续执行，Orchestrator做新决策
            "finalize": "finalize",  # 结束
        },
    )

    # 可选：添加memory节点（根据需要在continue时压缩记忆）
    # 这里简化为直接从reflector或continue回到orchestrator

    # finalize -> END
    workflow.add_edge("finalize", END)

    # 编译工作流
    return workflow.compile()


async def _parallel_join_node(state: GraphState) -> dict[str, Any]:
    """并行汇聚节点.

    收集所有安全专家（或传统Agent）的执行结果，准备下一轮。

    功能：
    1. 汇总本轮所有Agent的执行结果
    2. 创建轮次记录
    3. 更新轮次计数
    4. 清空本轮 agent_results（使用 None 触发 merge_or_clear_lists 清空）
    """
    from backend.models.agent import RoundRecord

    # 创建轮次记录
    round_record = RoundRecord(
        round_index=state.current_round,
        orchestrator_plan=state.current_plan,
        sub_tasks=state.sub_tasks,
        agent_results=state.agent_results,
    )

    # 更新轮次计数
    # sub_tasks 不再使用 merge_lists，每轮由 orchestrator 替换
    # agent_results 使用 None 触发 merge_or_clear_lists 清空
    return {
        "rounds": [round_record.model_dump()],
        "current_round": state.current_round + 1,
        "agent_results": None,  # 清空当前结果 (merge_or_clear_lists 收到 None 时返回 [])
    }


class WorkflowRunner:
    """工作流运行器.

    封装工作流的执行和状态管理。
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client
        self.workflow = build_workflow(llm_client)

    async def run(
        self,
        goal: str,
        context: str = "",
        max_rounds: int = 20,
    ) -> GraphState:
        """运行工作流.

        Args:
            goal: 任务目标
            context: 上下文
            max_rounds: 最大轮数

        Returns:
            最终状态
        """
        from backend.models.memory import MemoryDigest

        # 初始化状态
        initial_state = GraphState(
            task_id=self._generate_task_id(),
            goal=goal,
            context=context,
            max_rounds=max_rounds,
            memory_digest=MemoryDigest(),
        )

        # 执行工作流
        final_state = await self.workflow.ainvoke(initial_state.model_dump())

        return GraphState(**final_state)

    async def stream_run(
        self,
        goal: str,
        context: str = "",
        max_rounds: int = 20,
    ):
        """流式运行工作流.

        每完成一个节点就yield一次状态更新。
        """
        from backend.models.memory import MemoryDigest

        initial_state = GraphState(
            task_id=self._generate_task_id(),
            goal=goal,
            context=context,
            max_rounds=max_rounds,
            memory_digest=MemoryDigest(),
        )

        async for state in self.workflow.astream(initial_state.model_dump()):
            yield state

    @staticmethod
    def _generate_task_id() -> str:
        """生成任务ID."""
        import uuid

        return uuid.uuid4().hex[:12]

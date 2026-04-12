"""LangGraph节点定义 — 各Agent的执行节点."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.agents import (
    ExecutorAgent,
    MemoryAgent,
    OrchestratorAgent,
    ReflectorAgent,
    ThinkerAgent,
)
from backend.agents.security_experts import (
    WebSecurityExpert,
    NetworkPenetrationExpert,
    CodeAuditorExpert,
    MobileSecurityExpert,
    SecurityOpsExpert,
)
from backend.core.llm_client import LLMClient
from backend.models.agent import AgentResult, AgentRole, RoundRecord
from backend.models.state import GraphState
from backend.tools.registry import create_default_registry


def _safe_context(context: dict | None) -> dict[str, Any]:
    """将 input_context 中的 Pydantic 模型等非 JSON 安全对象转为可序列化形式."""
    if not context:
        return {}
    safe = {}
    for k, v in context.items():
        if hasattr(v, 'model_dump'):
            safe[k] = v.model_dump()
        elif isinstance(v, list):
            safe[k] = [
                item.model_dump() if hasattr(item, 'model_dump') else item
                for item in v
            ]
        else:
            safe[k] = v
    return safe


def _build_trace_event(agent: Any, node_name: str, result: Any = None, context: dict | None = None) -> dict[str, Any]:
    """从Agent中提取追踪事件."""
    traces = agent.get_and_clear_traces() if hasattr(agent, 'get_and_clear_traces') else []
    
    role = getattr(agent, 'role', node_name)
    role_str = role.value if hasattr(role, 'value') else str(role)
    
    event = {
        "event_type": "agent_execution",
        "node_name": node_name,
        "agent_name": getattr(agent, 'name', node_name),
        "agent_role": role_str,
        "model": getattr(getattr(agent, 'config', None), 'model', 'unknown'),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_calls": traces,
        "input_context": _safe_context(context),
    }
    
    if result is not None:
        if hasattr(result, 'summary'):
            event["result_summary"] = result.summary
            event["result_output"] = result.output
            event["result_status"] = result.status
            event["result_clues"] = [{"key": c.get("key"), "value": c.get("value")} for c in (result.clues or [])]
            # 提取工具调用记录（含执行结果）
            if hasattr(result, 'tool_calls') and result.tool_calls:
                event["tool_calls"] = result.tool_calls
        elif isinstance(result, dict):
            event["result_summary"] = result.get("summary", "")
            event["result_output"] = result.get("output", str(result))
            if result.get("tool_calls"):
                event["tool_calls"] = result["tool_calls"]
    
    return event


class AgentNodes:
    """Agent节点集合.

    每个节点接收GraphState，执行相应Agent的逻辑，返回更新后的状态。
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client

        # 创建工具注册表
        tool_registry = create_default_registry()

        # 初始化各Agent
        self.orchestrator = OrchestratorAgent(llm_client=llm_client)
        self.thinker = ThinkerAgent(llm_client=llm_client)
        self.executor = ExecutorAgent(llm_client=llm_client, tool_registry=tool_registry)
        self.reflector = ReflectorAgent(llm_client=llm_client)
        self.memory = MemoryAgent(llm_client=llm_client)

        # 初始化安全专家团队
        self.web_security = WebSecurityExpert(llm_client=llm_client)
        self.network_penetration = NetworkPenetrationExpert(llm_client=llm_client)
        self.code_auditor = CodeAuditorExpert(llm_client=llm_client)
        self.mobile_security = MobileSecurityExpert(llm_client=llm_client)
        self.security_ops = SecurityOpsExpert(llm_client=llm_client)

    async def orchestrator_node(self, state: GraphState) -> dict[str, Any]:
        """决策Agent节点.

        负责任务规划、子任务拆分。
        """
        # 准备记忆文本
        memory_text = ""
        if state.memory_digest:
            memory_text = state.memory_digest.to_prompt_text()

        # 获取之前的结果
        previous_results = []
        if state.rounds:
            last_round = state.rounds[-1]
            # 兼容 RoundRecord 对象和字典两种形式
            if isinstance(last_round, dict):
                agent_results = last_round.get("agent_results", [])
            else:
                agent_results = last_round.agent_results
            
            for r in agent_results:
                if isinstance(r, dict):
                    prev = {
                        "role": r.get("role", "unknown"),
                        "status": r.get("status", ""),
                        "summary": r.get("summary", ""),
                        "output": r.get("output", ""),
                        "clues": r.get("clues", []),
                    }
                    # 包含工具调用结果（截取，避免过长）
                    if r.get("tool_calls"):
                        tc_summary = []
                        for tc in r["tool_calls"]:
                            res = tc.get("result", {})
                            res_inner = res.get("result", res)
                            out = res_inner.get("output", "") if isinstance(res_inner, dict) else str(res_inner)
                            tc_summary.append({
                                "tool": tc.get("tool"),
                                "params": tc.get("params"),
                                "success": res_inner.get("success") if isinstance(res_inner, dict) else None,
                                "output": out[:2000] if out else "",
                            })
                        prev["tool_results"] = tc_summary
                    previous_results.append(prev)
                else:
                    prev = {
                        "role": r.role,
                        "status": r.status,
                        "summary": r.summary,
                        "output": r.output,
                        "clues": r.clues,
                    }
                    if hasattr(r, 'tool_calls') and r.tool_calls:
                        tc_summary = []
                        for tc in r.tool_calls:
                            res = tc.get("result", {})
                            res_inner = res.get("result", res)
                            out = res_inner.get("output", "") if isinstance(res_inner, dict) else str(res_inner)
                            tc_summary.append({
                                "tool": tc.get("tool"),
                                "params": tc.get("params"),
                                "success": res_inner.get("success") if isinstance(res_inner, dict) else None,
                                "output": out[:2000] if out else "",
                            })
                        prev["tool_results"] = tc_summary
                    previous_results.append(prev)

        input_context = {
            "round_index": state.current_round,
            "memory_text": memory_text,
            "previous_results": previous_results,
            "available_agents": [
                "web_security", "network_penetration", "code_auditor",
                "mobile_security", "security_ops", "thinker", "executor",
            ],
        }

        # 执行决策
        try:
            result = await self.orchestrator.execute(
                task=state.goal,
                context=input_context,
            )
        except Exception as e:
            print(f"[Nexus] Orchestrator 执行失败: {e}")
            traces = self.orchestrator.get_and_clear_traces() if hasattr(self.orchestrator, 'get_and_clear_traces') else []
            trace_event = {
                "event_type": "agent_execution",
                "node_name": "orchestrator",
                "agent_name": getattr(self.orchestrator, 'name', 'orchestrator'),
                "agent_role": "orchestrator",
                "model": getattr(getattr(self.orchestrator, 'config', None), 'model', 'unknown'),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "llm_calls": traces,
                "input_context": _safe_context(input_context),
                "result_summary": f"❌ 协调指挥官执行失败: {e}",
                "result_status": "failed",
            }
            # 失败时直接结束任务
            return {
                "current_plan": f"Orchestrator执行失败: {e}",
                "sub_tasks": [],
                "should_continue": False,
                "trace_events": [trace_event],
            }

        # 构建追踪事件
        trace_event = _build_trace_event(
            self.orchestrator, "orchestrator", result, input_context
        )

        # 提取子任务信息
        sub_tasks = []
        for clue in result.clues:
            if clue.get("key") == "sub_tasks":
                try:
                    sub_tasks = json.loads(clue.get("value", "[]"))
                except json.JSONDecodeError:
                    pass

        # 更新状态
        return {
            "current_plan": result.output,
            "sub_tasks": sub_tasks,
            "should_continue": not (
                result.clues
                and any(
                    c.get("key") == "is_completed" and c.get("value") == "True"
                    for c in result.clues
                )
            ),
            "trace_events": [trace_event],
        }

    async def thinker_node(self, state: GraphState) -> dict[str, Any]:
        """思考专家节点."""
        # 获取分配给thinker的子任务
        thinker_tasks = [
            t
            for t in state.sub_tasks
            if t.get("agent_role") == "thinker" and t.get("status") == "pending"
        ]

        if not thinker_tasks:
            return {"agent_results": [], "trace_events": []}

        results = []
        trace_events = []
        for task_data in thinker_tasks:
            task_desc = task_data.get("description", "")

            input_context = {
                "goal": state.goal,
                "round": state.current_round,
                "memory": state.memory_digest.to_prompt_text() if state.memory_digest else "",
            }

            result = await self.thinker.execute(
                task=task_desc,
                context=input_context,
            )

            # 构建追踪事件
            trace_event = _build_trace_event(self.thinker, "thinker", result, input_context)
            trace_events.append(trace_event)

            # 标记任务完成
            task_data["status"] = "completed"
            task_data["result"] = result.summary

            results.append(result)

        return {"agent_results": [r.model_dump() for r in results], "trace_events": trace_events}

    async def executor_node(self, state: GraphState) -> dict[str, Any]:
        """执行专家节点."""
        # 获取分配给executor的子任务
        executor_tasks = [
            t
            for t in state.sub_tasks
            if t.get("agent_role") == "executor" and t.get("status") == "pending"
        ]

        if not executor_tasks:
            return {"agent_results": [], "trace_events": []}

        results = []
        spawn_requests = []
        trace_events = []

        for task_data in executor_tasks:
            task_desc = task_data.get("description", "")

            input_context = {
                "goal": state.goal,
                "round": state.current_round,
                "memory": state.memory_digest.to_prompt_text() if state.memory_digest else "",
            }

            result = await self.executor.execute(
                task=task_desc,
                context=input_context,
            )

            # 构建追踪事件（含工具调用结果）
            trace_event = _build_trace_event(self.executor, "executor", result, input_context)
            trace_events.append(trace_event)

            # 标记任务完成
            task_data["status"] = "completed"
            task_data["result"] = result.summary

            results.append(result)

            # 收集子Agent派生请求
            for clue in result.clues:
                if clue.get("key") == "spawn_requests":
                    try:
                        requests = json.loads(clue.get("value", "[]"))
                        spawn_requests.extend(requests)
                    except json.JSONDecodeError:
                        pass

        return {
            "agent_results": [r.model_dump() for r in results],
            "spawn_requests": spawn_requests,
            "trace_events": trace_events,
        }

    async def reflector_node(self, state: GraphState) -> dict[str, Any]:
        """反思Agent节点."""
        # 兼容字典和对象
        recent_rounds = [
            r if isinstance(r, dict) else r.model_dump()
            for r in state.rounds[-3:]
        ]
        
        # 检查是否需要反思
        if not self.reflector.should_reflect(
            round_index=state.current_round,
            recent_rounds=recent_rounds,
        ):
            return {"reflection_result": None, "trace_events": []}

        all_rounds = [
            r if isinstance(r, dict) else r.model_dump()
            for r in state.rounds
        ]

        input_context = {
            "memory": state.memory_digest,
            "rounds": all_rounds,
        }

        try:
            result = await self.reflector.execute(
                task=state.goal,
                context=input_context,
            )
        except Exception as e:
            print(f"[Nexus] Reflector 执行失败: {e}，跳过反思")
            traces = self.reflector.get_and_clear_traces() if hasattr(self.reflector, 'get_and_clear_traces') else []
            trace_event = {
                "event_type": "agent_execution",
                "node_name": "reflector",
                "agent_name": getattr(self.reflector, 'name', 'reflector'),
                "agent_role": "reflector",
                "model": getattr(getattr(self.reflector, 'config', None), 'model', 'unknown'),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "llm_calls": traces,
                "input_context": _safe_context({"round_count": len(state.rounds), "goal": state.goal}),
                "result_summary": f"❌ 反思执行失败: {e}，已跳过",
                "result_status": "failed",
            }
            return {"reflection_result": None, "trace_events": [trace_event]}

        # 构建追踪事件
        trace_event = _build_trace_event(self.reflector, "reflector", result, {
            "round_count": len(state.rounds),
            "goal": state.goal,
        })

        # 检查是否需要调整策略
        should_adjust = False
        try:
            output = result.output
            if isinstance(output, dict):
                should_adjust = output.get("should_adjust_strategy", False)
            elif isinstance(output, str):
                output_dict = json.loads(output)
                should_adjust = output_dict.get("should_adjust_strategy", False)
        except (json.JSONDecodeError, AttributeError):
            pass

        return {
            "reflection_result": result.summary,
            "is_stalled": should_adjust,
            "trace_events": [trace_event],
        }

    async def memory_node(self, state: GraphState) -> dict[str, Any]:
        """记忆Agent节点."""
        # 检查是否需要压缩
        last_round_idx = state.memory_digest.covered_until_round if state.memory_digest else 0
        current_round = state.current_round

        if not self.memory.should_compress(
            current_round=current_round,
            last_compressed_round=last_round_idx,
            event_count=len(state.recent_clues),
            last_covered_event_count=state.memory_digest.covered_event_count
            if state.memory_digest
            else 0,
            estimated_tokens=len(str(state.rounds)),  # 简化的token估算
        ):
            return {}

        # 获取待压缩的轮次
        pending_rounds = []
        for r in state.rounds:
            rd = r if isinstance(r, dict) else r.model_dump()
            if rd.get("round_index", 0) > last_round_idx:
                pending_rounds.append(rd)

        result = await self.memory.execute(
            task=state.goal,
            context={
                "previous_digest": state.memory_digest,
                "pending_rounds": pending_rounds,
                "pending_clues": state.recent_clues,
            },
        )

        # 解析新的记忆摘要
        try:
            output = result.output
            if isinstance(output, str):
                digest_data = json.loads(output)
            else:
                digest_data = output

            from backend.models.memory import MemoryDigest

            new_digest = MemoryDigest(**digest_data)
        except (json.JSONDecodeError, TypeError):
            new_digest = None

        return {
            "memory_digest": new_digest,
            "recent_clues": [],  # 清空已压缩的线索
        }

    async def finalize_node(self, state: GraphState) -> dict[str, Any]:
        """最终化节点.

        整合所有结果，生成最终输出。
        """
        # 获取所有执行结果
        all_results = []
        for round_record in state.rounds:
            if isinstance(round_record, dict):
                all_results.extend(round_record.get("agent_results", []))
            else:
                all_results.extend(round_record.agent_results)

        # 构建最终答案
        final_result = f"任务: {state.goal}\n\n"
        final_result += f"执行轮数: {state.current_round}\n"
        final_result += f"最终结果:\n{state.final_result or '任务未完成'}\n"

        trace_event = {
            "event_type": "finalize",
            "node_name": "finalize",
            "agent_name": "最终汇总",
            "agent_role": "system",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result_summary": f"共执行{state.current_round}轮，涉及{len(all_results)}个Agent结果",
            "result_output": final_result,
            "llm_calls": [],
            "input_context": {},
        }

        return {
            "final_result": final_result,
            "is_completed": True,
            "should_continue": False,
            "trace_events": [trace_event],
        }

    # ============ 安全专家节点 ============

    async def _expert_node(self, state: GraphState, expert_agent: Any, role: str) -> dict[str, Any]:
        """通用安全专家节点处理.

        Args:
            state: 当前状态
            expert_agent: 专家Agent实例
            role: 专家角色名称

        Returns:
            执行结果
        """
        # 获取分配给该专家的子任务
        expert_tasks = [
            t
            for t in state.sub_tasks
            if t.get("agent_role") == role and t.get("status") == "pending"
        ]

        if not expert_tasks:
            return {"agent_results": [], "trace_events": []}

        # 收集其他专家的已有结果（用于协同）
        other_expert_results = {}
        for result in state.agent_results:
            result_role = result.get("role", "")
            if result_role != role and result_role in [
                "web_security",
                "network_penetration",
                "code_auditor",
                "mobile_security",
                "security_ops",
            ]:
                other_expert_results[result_role] = result.get("summary", "")

        results = []
        trace_events = []
        for task_data in expert_tasks:
            task_desc = task_data.get("description", "")

            input_context = {
                "goal": state.goal,
                "round": state.current_round,
                "memory": state.memory_digest.to_prompt_text() if state.memory_digest else "",
                "other_expert_results": other_expert_results,
                "task_description": task_desc,
            }

            try:
                result = await expert_agent.execute(
                    task=task_desc,
                    context=input_context,
                )

                # 构建追踪事件
                trace_event = _build_trace_event(expert_agent, role, result, input_context)
                trace_events.append(trace_event)

                # 标记任务完成
                task_data["status"] = "completed"
                task_data["result"] = result.summary
            except Exception as e:
                print(f"[Nexus] Agent {role} 执行失败: {e}")
                # 收集已有的trace记录
                traces = expert_agent.get_and_clear_traces() if hasattr(expert_agent, 'get_and_clear_traces') else []
                role_str = role
                trace_event = {
                    "event_type": "agent_execution",
                    "node_name": role,
                    "agent_name": getattr(expert_agent, 'name', role),
                    "agent_role": role_str,
                    "model": getattr(getattr(expert_agent, 'config', None), 'model', 'unknown'),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "llm_calls": traces,
                    "input_context": _safe_context(input_context),
                    "result_summary": f"❌ 执行失败: {e}",
                    "result_status": "failed",
                }
                trace_events.append(trace_event)

                task_data["status"] = "failed"
                task_data["result"] = str(e)

                result = AgentResult(
                    agent_id=getattr(expert_agent, 'agent_id', role),
                    role=role,
                    status="failed",
                    summary=f"Agent执行失败: {e}",
                    output=str(e),
                    clues=[],
                )

            results.append(result)

        return {
            "agent_results": [r.model_dump() for r in results],
            "trace_events": trace_events,
        }

    async def web_security_node(self, state: GraphState) -> dict[str, Any]:
        """Web安全专家节点."""
        return await self._expert_node(state, self.web_security, "web_security")

    async def network_penetration_node(self, state: GraphState) -> dict[str, Any]:
        """网络渗透专家节点."""
        return await self._expert_node(state, self.network_penetration, "network_penetration")

    async def code_auditor_node(self, state: GraphState) -> dict[str, Any]:
        """代码审计专家节点."""
        return await self._expert_node(state, self.code_auditor, "code_auditor")

    async def mobile_security_node(self, state: GraphState) -> dict[str, Any]:
        """移动安全专家节点."""
        return await self._expert_node(state, self.mobile_security, "mobile_security")

    async def security_ops_node(self, state: GraphState) -> dict[str, Any]:
        """安全运营专家节点."""
        return await self._expert_node(state, self.security_ops, "security_ops")

    async def memory_node(self, state: GraphState) -> dict[str, Any]:
        """记忆Agent节点（简化为空实现，避免编译问题）."""
        return {}

    async def thinker_node(self, state: GraphState) -> dict[str, Any]:
        """思考专家节点（向后兼容）."""
        return await self._expert_node(state, self.thinker, "thinker")

    async def executor_node(self, state: GraphState) -> dict[str, Any]:
        """执行专家节点（向后兼容）."""
        return await self._expert_node(state, self.executor, "executor")

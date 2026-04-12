"""FastAPI主应用 — 包含WebSocket支持."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.a2a.bus import MessageBus
from backend.config.settings import get_settings
from backend.core.llm_client import LLMClientFactory
from backend.graph.workflow import WorkflowRunner
from backend.models.task import TaskRequest, TaskResponse


# 内存中的任务存储
_tasks_db: dict[str, dict[str, Any]] = {}


# 全局状态
message_bus = MessageBus()
workflow_runner: WorkflowRunner | None = None
active_connections: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 轻量化启动，懒加载工作流."""
    settings = get_settings()
    print(f"[Nexus] 服务启动于 {settings.server.host}:{settings.server.port}")

    yield

    # 关闭时清理
    for ws in active_connections:
        await ws.close()
    print("[Nexus] 服务已关闭")


_workflow_runner_instance: WorkflowRunner | None = None


def get_workflow_runner() -> WorkflowRunner:
    """懒加载工作流运行器 — 首次调用时才初始化."""
    global _workflow_runner_instance
    if _workflow_runner_instance is None:
        print("[Nexus] 初始化工作流运行器（首次）...")
        llm_client = LLMClientFactory.get_client()
        _workflow_runner_instance = WorkflowRunner(llm_client)
        print("[Nexus] 工作流运行器初始化完成")
    return _workflow_runner_instance


def create_app() -> FastAPI:
    """创建FastAPI应用."""
    app = FastAPI(
        title="Nexus Multi-Agent System",
        description="基于LangGraph的多Agent协作系统",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API路由
    app.include_router(api_router, prefix="/api")

    # 静态文件 - 前端
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 根路径返回index.html
    @app.get("/")
    async def root():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Nexus Multi-Agent System API"}

    return app


from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health")
async def health_check() -> dict[str, str]:
    """健康检查."""
    return {"status": "ok", "version": "0.1.0"}


async def _run_task_background(task_id: str, goal: str, context: str, max_rounds: int) -> None:
    """后台运行工作流任务."""
    import traceback as tb
    runner = get_workflow_runner()
    try:
        async for state_update in runner.stream_run(goal, context, max_rounds):
            for node_name, node_output in state_update.items():
                if not isinstance(node_output, dict):
                    continue
                # 更新进度信息
                if "current_round" in node_output:
                    _tasks_db[task_id]["current_round"] = node_output["current_round"]
                if "final_result" in node_output:
                    _tasks_db[task_id]["result"] = node_output["final_result"]
                # 收集追踪事件
                events = node_output.get("trace_events", [])
                if events:
                    _tasks_db[task_id]["trace_events"].extend(events)
                # 记录当前执行的节点
                _tasks_db[task_id]["current_node"] = node_name
                print(f"[Nexus] 任务 {task_id} | 节点: {node_name} | 轮次: {_tasks_db[task_id].get('current_round', 0)}")

        _tasks_db[task_id]["status"] = "completed"
        _tasks_db[task_id]["current_node"] = None
        print(f"[Nexus] 任务 {task_id} 已完成")
    except Exception as e:
        err_detail = tb.format_exc()
        print(f"[Nexus] 任务 {task_id} 执行失败:\n{err_detail}")
        _tasks_db[task_id]["status"] = "failed"
        _tasks_db[task_id]["error"] = str(e)
        _tasks_db[task_id]["current_node"] = None


@api_router.post("/tasks")
async def create_task(request: TaskRequest) -> dict[str, Any]:
    """创建新任务 — 后台异步执行，立即返回任务ID."""
    import asyncio

    # 确保工作流运行器已初始化
    get_workflow_runner()

    # 生成任务ID
    task_id = uuid.uuid4().hex[:12]

    # 存储任务初始状态
    _tasks_db[task_id] = {
        "task_id": task_id,
        "goal": request.goal,
        "context": request.context,
        "status": "running",
        "current_round": 0,
        "current_node": None,
        "result": None,
        "error": None,
        "trace_events": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # 在后台启动工作流
    asyncio.create_task(
        _run_task_background(task_id, request.goal, request.context, request.max_rounds)
    )

    print(f"[Nexus] 任务 {task_id} 已创建，后台执行中...")
    return {"task_id": task_id, "status": "running"}


@api_router.get("/tasks")
async def list_tasks() -> list[dict[str, Any]]:
    """获取所有任务列表."""
    return list(_tasks_db.values())


@api_router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """获取任务状态（可用于轮询进度）."""
    task = _tasks_db.get(task_id)
    if task:
        return task
    return {"task_id": task_id, "status": "not_found", "error": "Task not found"}


@api_router.get("/tasks/{task_id}/trace")
async def get_task_trace(task_id: str) -> dict[str, Any]:
    """获取任务的完整执行追踪（Agent思考流程）."""
    task = _tasks_db.get(task_id)
    if not task:
        return {"task_id": task_id, "error": "Task not found", "trace_events": []}
    return {
        "task_id": task_id,
        "goal": task.get("goal", ""),
        "status": task.get("status", ""),
        "trace_events": task.get("trace_events", []),
    }


@api_router.get("/tools")
async def list_tools() -> list[dict[str, Any]]:
    """列出所有可用工具."""
    from backend.tools.registry import create_default_registry

    registry = create_default_registry()
    tools = registry.list_tools()

    return [
        {
            "name": t.name,
            "description": t.description,
            "source": t.source,
            "parameters": t.parameters,
        }
        for t in tools
    ]


@api_router.get("/skills")
async def list_skills() -> dict[str, Any]:
    """列出所有Skills（树状结构）."""
    from backend.skills.manager import SkillManager

    manager = SkillManager()
    manager.load_all()

    def node_to_dict(node: Any) -> dict[str, Any]:
        return {
            "name": node.name,
            "path": node.path,
            "is_category": node.is_category,
            "children": [node_to_dict(c) for c in node.children],
            "skill": node.skill.model_dump() if node.skill else None,
        }

    tree = manager.get_tree()
    return {
        "tree": node_to_dict(tree) if tree else None,
        "total": len(manager.list_all()),
    }


@api_router.get("/skills/{full_name:path}")
async def get_skill(full_name: str) -> dict[str, Any] | None:
    """获取特定Skill."""
    from backend.skills.manager import SkillManager

    manager = SkillManager()
    manager.load_all()

    skill = manager.get_skill(full_name)
    if skill:
        return skill.model_dump()
    return None


@api_router.get("/config/agents")
async def get_agent_configs() -> dict[str, Any]:
    """获取Agent配置."""
    from backend.core.config_manager import get_config_manager

    config_manager = get_config_manager()
    return config_manager.load_yaml_config("agents.yaml")


@api_router.get("/config/agents/{role}")
async def get_agent_config(role: str) -> dict[str, Any]:
    """获取单个Agent配置."""
    from backend.core.config_manager import get_config_manager

    config_manager = get_config_manager()
    configs = config_manager.load_yaml_config("agents.yaml")
    if role not in configs:
        return {"error": "Agent not found"}
    return configs[role]


@api_router.put("/config/agents/{role}")
async def update_agent_config(role: str, config: dict[str, Any]) -> dict[str, Any]:
    """更新Agent配置."""
    from backend.core.config_manager import get_config_manager

    config_manager = get_config_manager()
    configs = config_manager.load_yaml_config("agents.yaml")

    if role not in configs:
        return {"error": "Agent not found"}

    # 更新配置
    configs[role].update(config)
    config_manager.save("agents.yaml", configs)

    return {"status": "ok", "role": role, "config": configs[role]}


@api_router.post("/config/agents/{role}/prompt")
async def update_agent_prompt(role: str, request: dict[str, str]) -> dict[str, str]:
    """更新Agent提示词."""
    from backend.core.config_manager import get_config_manager

    prompt = request.get("prompt", "")
    config_manager = get_config_manager()
    config_manager.update_agent_prompt(role, prompt)

    return {"status": "ok", "role": role}


# Skills管理API
@api_router.get("/config/skills/raw")
async def get_skills_raw_config() -> dict[str, Any]:
    """获取Skills原始配置."""
    from backend.core.config_manager import get_config_manager

    config_manager = get_config_manager()
    return config_manager.load_yaml_config("skills.yaml")


@api_router.put("/config/skills/raw")
async def update_skills_raw_config(config: dict[str, Any]) -> dict[str, Any]:
    """更新Skills原始配置."""
    from backend.core.config_manager import get_config_manager

    config_manager = get_config_manager()
    config_manager.save("skills.yaml", config)

    return {"status": "ok", "config": config}


@api_router.post("/config/skills/{category:path}")
async def create_skill_category(category: str, data: dict[str, Any]) -> dict[str, Any]:
    """创建新的Skill分类或条目."""
    from backend.core.config_manager import get_config_manager

    config_manager = get_config_manager()
    configs = config_manager.load_yaml_config("skills.yaml")

    # 按路径创建嵌套结构
    parts = category.split("/")
    current = configs
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    # 设置值
    current[parts[-1]] = data
    config_manager.save("skills.yaml", configs)

    return {"status": "ok", "path": category}


@api_router.delete("/config/skills/{category:path}")
async def delete_skill_category(category: str) -> dict[str, Any]:
    """删除Skill分类或条目."""
    from backend.core.config_manager import get_config_manager

    config_manager = get_config_manager()
    configs = config_manager.load_yaml_config("skills.yaml")

    # 按路径删除
    parts = category.split("/")
    current = configs
    for part in parts[:-1]:
        if part not in current:
            return {"error": "Path not found"}
        current = current[part]

    if parts[-1] in current:
        del current[parts[-1]]
        config_manager.save("skills.yaml", configs)
        return {"status": "ok", "path": category}

    return {"error": "Category not found"}


# LLM配置管理
_llm_config: dict[str, Any] = {}


@api_router.get("/config/llm")
async def get_llm_config() -> dict[str, Any]:
    """获取LLM配置（合并前端设定和后端默认值）."""
    global _llm_config
    settings = get_settings()

    # 优先使用前端设定的配置，然后是后端默认值
    config = {
        "api_key": _llm_config.get("api_key") or settings.llm.api_key or "",
        "base_url": _llm_config.get("base_url") or settings.llm.base_url,
        "model": _llm_config.get("model") or settings.llm.default_model,
        "timeout": _llm_config.get("timeout") or settings.llm.timeout,
        "max_retries": _llm_config.get("max_retries") or settings.llm.max_retries,
    }
    # 隐藏完整的API key
    result = dict(config)
    if result["api_key"]:
        result["api_key_masked"] = result["api_key"][:8] + "..." + result["api_key"][-4:]
        result["api_key_length"] = len(result["api_key"])
    result["has_api_key"] = bool(result["api_key"])
    # 不在GET响应中返回完整的api_key
    result.pop("api_key", None)
    return result


@api_router.put("/config/llm")
async def update_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    """更新LLM配置."""
    global _llm_config

    # 验证必需字段
    if not config.get("api_key"):
        return {"error": "API Key 不能为空"}

    _llm_config = {
        "api_key": config.get("api_key"),
        "base_url": config.get("base_url", "https://api.openai.com/v1"),
        "model": config.get("model", "gpt-4o"),
        "timeout": config.get("timeout", 60),
        "max_retries": config.get("max_retries", 3),
    }

    # 更新环境变量（当前进程）
    import os

    os.environ["LLM_API_KEY"] = _llm_config["api_key"]
    os.environ["LLM_BASE_URL"] = _llm_config["base_url"]
    os.environ["LLM_DEFAULT_MODEL"] = _llm_config["model"]

    # 清除LLM客户端缓存，强制下次重新创建
    from backend.core.llm_client import LLMClientFactory

    LLMClientFactory._client = None

    return {"status": "ok", "config": {k: v for k, v in _llm_config.items() if k != "api_key"}}


@api_router.post("/config/llm/test")
async def test_llm_connection() -> dict[str, Any]:
    """测试LLM连接."""
    try:
        from backend.core.llm_client import LLMClientFactory
        from backend.config.settings import get_settings

        settings = get_settings()
        
        # 检查API Key是否配置
        api_key = _llm_config.get("api_key") or settings.llm.api_key
        if not api_key:
            return {"status": "error", "message": "未配置 API Key，请在系统设置中配置"}
        
        # 创建新客户端（使用最新配置）
        base_url = _llm_config.get("base_url") or settings.llm.base_url
        model = _llm_config.get("model") or settings.llm.default_model
        
        client = LLMClientFactory.get_client(
            api_key=api_key,
            base_url=base_url,
        )

        # 尝试一个简单的请求
        import asyncio

        response = await asyncio.wait_for(
            client.complete(
                messages=[{"role": "user", "content": "Hi"}],
                model=model,
                max_tokens=5,
            ),
            timeout=10,
        )

        return {"status": "ok", "message": f"连接成功，模型: {model}"}
    except Exception as e:
        import traceback
        error_detail = f"{type(e).__name__}: {str(e)}"
        print(f"[LLM Test Error] {error_detail}")
        print(traceback.format_exc())
        return {"status": "error", "message": error_detail}


# WebSocket路由
@api_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点 — 实时任务流（含Agent思考流程追踪）."""
    await websocket.accept()
    active_connections.append(websocket)

    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "start_task":
                # 启动任务流式执行
                goal = message.get("goal", "")
                context = message.get("context", "")
                task_id = uuid.uuid4().hex[:12]

                # 存储任务
                _tasks_db[task_id] = {
                    "task_id": task_id,
                    "goal": goal,
                    "context": context,
                    "status": "running",
                    "current_round": 0,
                    "result": None,
                    "error": None,
                    "trace_events": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                await websocket.send_json({
                    "type": "task_created",
                    "task_id": task_id,
                })

                try:
                    runner = get_workflow_runner()
                    async for state_update in runner.stream_run(goal, context):
                        # 提取追踪事件和进度
                        trace_events = []
                        current_node = None
                        for node_name, node_output in state_update.items():
                            if isinstance(node_output, dict):
                                events = node_output.get("trace_events", [])
                                if events:
                                    trace_events.extend(events)
                                    _tasks_db[task_id]["trace_events"].extend(events)
                                current_node = node_name
                                if "current_round" in node_output:
                                    _tasks_db[task_id]["current_round"] = node_output["current_round"]

                        # 发送状态更新（使用 default=str 避免序列化错误）
                        try:
                            await websocket.send_text(json.dumps({
                                "type": "state_update",
                                "task_id": task_id,
                                "node": current_node,
                                "trace_events": trace_events,
                            }, ensure_ascii=False, default=str))
                        except Exception as ser_err:
                            print(f"[Nexus] WebSocket序列化错误: {ser_err}")

                    _tasks_db[task_id]["status"] = "completed"
                    await websocket.send_json({
                        "type": "task_complete",
                        "task_id": task_id,
                    })
                except Exception as e:
                    _tasks_db[task_id]["status"] = "failed"
                    _tasks_db[task_id]["error"] = str(e)
                    await websocket.send_json({
                        "type": "task_error",
                        "task_id": task_id,
                        "error": str(e),
                    })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "error": str(e),
        })
        if websocket in active_connections:
            active_connections.remove(websocket)


@api_router.websocket("/ws/monitor")
async def monitor_websocket(websocket: WebSocket):
    """WebSocket端点 — 实时监控消息总线."""
    await websocket.accept()
    active_connections.append(websocket)

    # 订阅消息总线
    async def forward_message(message: Any) -> None:
        try:
            await websocket.send_json(
                {
                    "type": "a2a_message",
                    "data": message.model_dump(),
                }
            )
        except Exception:
            pass

    # 订阅所有消息
    await message_bus.subscribe("*", forward_message)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "get_history":
                history = message_bus.get_history(limit=50)
                await websocket.send_json(
                    {
                        "type": "history",
                        "data": [h.model_dump() for h in history],
                    }
                )

    except WebSocketDisconnect:
        pass
    finally:
        await message_bus.unsubscribe("*", forward_message)
        if websocket in active_connections:
            active_connections.remove(websocket)


# 创建应用实例
app = create_app()

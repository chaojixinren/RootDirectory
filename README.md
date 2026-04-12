# Nexus — 多Agent安全协作系统

基于 **LangGraph + FastAPI** 的多Agent并行协作系统，专注于安全测试与分析场景。支持 5 类安全专家并行协作，内置 8 种工具，兼容 Windows/Linux 双平台。

## 架构概览

```
                              ┌─────────────┐
                              │    START     │
                              └──────┬──────┘
                                     ▼
                         ┌───────────────────────┐
                         │    Orchestrator       │◄───────────────────┐
                         │  (协调指挥官)          │                    │
                         │  分析任务、调度专家     │                    │
                         └───────────┬───────────┘                    │
                                     ▼                                │
              ┌──────────────────────────────────────────┐           │
              │     dispatch_security_experts            │           │
              │     (安全专家并行调度)                     │           │
              └──────────────────────────────────────────┘           │
                 │      │       │       │       │                    │
       ┌─────────┘      │       │       │       └──────────┐        │
       ▼                ▼       ▼       ▼                  ▼        │
  ┌──────────┐   ┌──────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ │
  │   Web    │   │ Network  │ │ Code   │ │ Mobile   │ │ Security │ │
  │ Security │   │Penetrate │ │Auditor │ │ Security │ │   Ops    │ │
  └────┬─────┘   └────┬─────┘ └───┬────┘ └────┬─────┘ └────┬─────┘ │
       └───────────────┴───────────┴───────────┴────────────┘       │
                                ▼                                    │
                     ┌──────────────────┐                           │
                     │  parallel_join   │                           │
                     │  (结果汇聚)       │                           │
                     └────────┬─────────┘                           │
                              ▼                                     │
                     ┌──────────────────┐                           │
                     │    Reflector     │                           │
                     │  (反思Agent)     │                           │
                     └────────┬─────────┘                           │
                              ▼                                     │
                    ┌────────────────────┐                          │
                    │  should_continue   │                          │
                    └──┬───────┬─────┬──┘                          │
                       │       │     │                              │
                ┌──────┘       │     └──────┐                       │
                ▼              ▼            ▼                       │
          ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
          │ finalize │  │  memory  │  │ continue │─────────────────┘
          │  (结束)  │  │(记忆压缩) │  │ (下一轮) │
          └────┬─────┘  └──────────┘  └──────────┘
               ▼
          ┌──────────┐
          │   END    │
          └──────────┘
```

## 核心特性

### 1. Agent 架构（7 类 Agent）

**核心Agent：**

| Agent | 角色 | 职责 |
|-------|------|------|
| **Orchestrator** | 协调指挥官 | 任务分解、专家调度、死循环检测、反重复探测 |
| **Executor** | 执行专家 | 调用工具执行具体操作，支持 Windows 命令适配 |
| **Thinker** | 思考专家 | 分析问题、设计方案、评估风险 |
| **Reflector** | 反思Agent | 5维度评估（任务理解、计划质量、执行质量、协作、信息流） |
| **Memory** | 记忆Agent | 每3轮压缩历史，保留关键决策和确认发现 |

**安全专家（并行执行）：**

| Agent | 角色 | 分析领域 |
|-------|------|---------|
| **WebSecurityExpert** | Web安全专家 | 认证/授权、输入处理、业务逻辑、浏览器侧风险 |
| **NetworkPenetrationExpert** | 网络渗透专家 | 主机发现、端口扫描、服务识别、内网渗透 |
| **CodeAuditorExpert** | 代码审计专家 | 源码审查、漏洞模式识别、依赖分析 |
| **MobileSecurityExpert** | 移动安全专家 | APP逆向、通信安全、本地存储、组件暴露 |
| **SecurityOpsExpert** | 安全运营专家 | 日志分析、入侵检测、应急响应、加固建议 |

### 2. 工具系统（8 种内置工具）

| 工具 | 功能说明 |
|------|---------|
| `file_read` | 读取文件内容 |
| `file_write` | 写入/创建文件 |
| `file_search` | 按模式搜索文件 |
| `list_dir` | 列出目录内容 |
| `shell_exec` | 执行 Shell 命令（Windows 自动适配） |
| `git` | Git 操作（status、diff、log 等） |
| `analyze_python` | Python 代码静态分析 |
| `find_todos` | 搜索代码中的 TODO/FIXME 注释 |

**Windows 命令适配**：`shell_exec` 自动将 Linux 命令转换为 Windows 等效命令（`head→more`、`grep→findstr`），自动将单引号转双引号。

### 3. MCP 协议支持

标准 MCP 客户端，支持三种传输方式：
- **STDIO** — 通过子进程标准输入输出通信
- **SSE** — Server-Sent Events 传输
- **HTTP** — 基于 HTTP 的 Streamable 传输

协议版本：`2024-11-05`

### 4. Skills 系统

树状分类的技能知识库，支持按场景自动注入到 Agent 上下文：

```
skills/
├── security/
│   └── pentest/        # 渗透测试技能
├── coding/
│   └── python/         # Python 编程技能
└── devops/
    └── docker/         # Docker 运维技能
```

每个 Skill 通过 YAML 定义 `name`、`description`、`when_to_use`、`content` 字段。

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆并进入项目
git clone <repo-url>
cd nexus

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 LLM_API_KEY 和 LLM_BASE_URL

# 3. 启动服务
docker-compose up -d

# 4. 访问
# 前端界面：http://localhost
# 后端API：http://localhost:8000
```

Docker Compose 包含两个服务：
- `backend`：Python 3.11-slim，端口 8000
- `frontend`：Nginx 代理，端口 80

### 方式二：本地开发

```bash
# 1. 安装依赖（Python >= 3.11）
pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 LLM_API_KEY

# 3. 启动后端（使用 create_app 工厂模式）
# Linux/macOS:
PYTHONPATH=$(pwd) python -m uvicorn backend.api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

# Windows PowerShell:
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn backend.api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

# 4. 访问 http://localhost:8000
```

> **注意**：`PYTHONPATH` 必须设为项目根目录的绝对路径，否则模块导入会失败。

## API 参考

### 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks` | 创建任务（异步执行，立即返回 task_id） |
| `GET` | `/api/tasks` | 获取所有任务列表 |
| `GET` | `/api/tasks/{task_id}` | 获取任务状态和结果（可轮询） |
| `GET` | `/api/tasks/{task_id}/trace` | 获取完整执行追踪（Agent 思考流程） |

**创建任务请求体：**
```json
{
  "goal": "对目标进行 Web 安全评估",
  "context": "目标地址：http://example.com",
  "max_rounds": 10
}
```

### 工具与技能

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tools` | 列出所有可用工具 |
| `GET` | `/api/skills` | 获取技能树（树状结构） |
| `GET` | `/api/skills/{full_name}` | 获取特定技能详情 |

### 配置管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/config/agents` | 获取所有 Agent 配置 |
| `GET` | `/api/config/agents/{role}` | 获取单个 Agent 配置 |
| `PUT` | `/api/config/agents/{role}` | 更新 Agent 配置 |
| `POST` | `/api/config/agents/{role}/prompt` | 更新 Agent 提示词 |
| `GET` | `/api/config/llm` | 获取 LLM 配置 |
| `PUT` | `/api/config/llm` | 更新 LLM 配置（运行时生效） |
| `POST` | `/api/config/llm/test` | 测试 LLM 连接 |

### Skills 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/config/skills/raw` | 获取 Skills 原始 YAML 配置 |
| `PUT` | `/api/config/skills/raw` | 更新 Skills 配置 |
| `POST` | `/api/config/skills/{category}` | 创建技能分类/条目 |
| `DELETE` | `/api/config/skills/{category}` | 删除技能分类/条目 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `WebSocket` | `/ws` | 实时消息推送（任务进度、Agent 输出） |

## 前端界面

内置单页 Web 界面（暗色主题），通过 `http://localhost:8000` 直接访问。

| 面板 | 功能 |
|------|------|
| **Dashboard** | 系统状态总览、快速操作 |
| **任务创建** | 输入目标、上下文、最大轮次，创建任务 |
| **Agent 配置** | 查看/修改各Agent的模型、温度、提示词 |
| **Skills 管理** | 树状浏览、搜索、创建/编辑/删除技能 |
| **工具配置** | 查看可用工具及参数、测试工具执行 |
| **执行监控** | 实时追踪任务进度、当前节点、Agent 输出 |
| **日志与追踪** | 完整执行历史、Agent 思考过程、工具调用结果 |

## 目录结构

```
nexus/
├── backend/                    # Python 后端
│   ├── agents/                 # Agent 实现
│   │   ├── base.py            # Agent 基类
│   │   ├── orchestrator.py    # 协调指挥官
│   │   ├── executor.py        # 执行专家
│   │   ├── thinker.py         # 思考专家
│   │   ├── reflector.py       # 反思Agent
│   │   ├── memory.py          # 记忆Agent
│   │   └── security_experts.py # 5类安全专家
│   ├── api/
│   │   └── main.py            # FastAPI 路由 + WebSocket
│   ├── config/
│   │   ├── settings.py        # Pydantic 配置系统
│   │   ├── agents.yaml        # Agent 角色配置
│   │   └── skills.yaml        # Skills 定义
│   ├── core/
│   │   ├── config_manager.py  # YAML 配置管理
│   │   └── llm_client.py      # LLM 客户端（OpenAI/百度千帆）
│   ├── graph/
│   │   ├── workflow.py        # LangGraph StateGraph 定义
│   │   ├── nodes.py           # 节点实现 + trace_events
│   │   └── edges.py           # 条件边 + 并行调度
│   ├── models/                 # Pydantic 数据模型
│   │   ├── state.py           # GraphState（工作流状态）
│   │   ├── agent.py           # AgentConfig / AgentResult
│   │   ├── tool.py            # ToolDefinition / ToolResult
│   │   └── skill.py           # Skill 模型
│   ├── skills/                 # Skills 管理
│   │   ├── manager.py         # 树状技能管理器
│   │   ├── loader.py          # YAML 加载器
│   │   └── injector.py        # 上下文注入器
│   ├── tools/
│   │   ├── registry.py        # 工具注册表 + 执行器
│   │   ├── executor.py        # 工具调用中间层
│   │   ├── cli/               # 内置 CLI 工具
│   │   │   ├── file_ops.py   # 文件读写/搜索/列目录
│   │   │   ├── shell_ops.py  # Shell 执行（Windows 适配）
│   │   │   └── code_ops.py   # 代码分析 / TODO 搜索
│   │   └── mcp/               # MCP 协议客户端
│   │       ├── client.py     # STDIO/SSE/HTTP 传输
│   │       └── registry.py   # MCP 工具注册
│   ├── a2a/                    # Agent-to-Agent 通信
│   │   ├── bus.py             # 消息总线
│   │   └── message.py         # 消息格式
│   └── static/
│       └── index.html          # 内置 Web 前端
├── config/                     # 全局配置（挂载到 Docker）
│   ├── agents.yaml
│   ├── skills.yaml
│   └── llm.local.yaml
├── prompts/                    # Agent 系统提示词文件
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── docker-compose.yml          # 生产部署
├── docker-compose.dev.yml      # 开发环境
├── pyproject.toml
└── .env.example
```

## 配置说明

### 环境变量（.env）

```bash
# LLM 配置（必填）
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_DEFAULT_MODEL=gpt-4o

# 可选：不同 Agent 使用不同模型
AGENT_ORCHESTRATOR_MODEL=gpt-4o
AGENT_THINKER_MODEL=gpt-4o
AGENT_EXECUTOR_MODEL=gpt-4o-mini
AGENT_REFLECTOR_MODEL=gpt-4o
AGENT_MEMORY_MODEL=gpt-4o-mini

# 工作流配置
WORKFLOW_MAX_ROUNDS=20          # 最大执行轮数
WORKFLOW_STALL_THRESHOLD=3      # 停滞检测阈值

# 服务器配置
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
SERVER_LOG_LEVEL=info
```

### Agent 配置（config/agents.yaml）

每个 Agent 可独立配置模型、温度、最大 Token、最大步数和系统提示词：

```yaml
orchestrator:
  name: "协调指挥官"
  model: "gpt-4o"
  temperature: 0.1
  max_tokens: 4000
  max_steps: 10
  system_prompt: |
    你是协调指挥官，负责任务分解和专家调度...

web_security:
  name: "Web安全专家"
  model: "gpt-4o"
  temperature: 0.1
  max_tokens: 4000
  max_steps: 20
  system_prompt: |
    你是Web安全专家...
```

### Skills 配置（config/skills.yaml）

```yaml
security:
  pentest:
    info_gathering:
      name: "信息收集"
      description: "渗透测试中的信息收集技术"
      when_to_use: "需要进行信息收集时"
      content: |
        # 信息收集技能
        ...
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 工作流引擎 | LangGraph >= 0.4.0 |
| LLM 框架 | LangChain Core >= 0.3.0 |
| Web 框架 | FastAPI >= 0.115.0 |
| 数据模型 | Pydantic >= 2.0 |
| HTTP 客户端 | httpx >= 0.28.0 |
| 配置管理 | pydantic-settings + PyYAML |
| 运行时 | Python >= 3.11, uvicorn |
| 容器化 | Docker + docker-compose |

## License

MIT

## API文档

启动后端后访问 http://localhost:8000/docs 查看自动生成的API文档。

## 技术栈

- **后端**: Python 3.11, LangGraph, FastAPI, Pydantic
- **前端**: Vue3, Vite, Element Plus, ECharts
- **部署**: Docker, Docker Compose

## 许可证

MIT License

# AGENTS.md — UF Stock Assistant

> 本文件面向 AI 编程助手。如果你第一次接触这个仓库，请先阅读本文，再按需深入 `docs/` 目录。

---

## 项目概览

`uf-stock-assistant` 是一个基于 LangChain 框架构建的智能股票助手 Agent，支持股票数据分析、交易策略执行、虚拟货币行情、市场分析、自动选股、下单模拟等功能。

- **项目名称**：`uf-stock-assistant`
- **版本**：`0.1.0`
- **Python 版本要求**：`>= 3.11`
- **核心目标**：构建一个具备专业知识、可扩展的企业级股票助手智能体

端到端链路：

```
用户请求 -> 对话管理 -> Agent 路由 -> 工具调用 -> 数据处理 -> LLM 推理 -> 格式化输出
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| AI 框架 | LangChain + LangGraph |
| LLM 调用 | 自研 HTTP 客户端（参考 condex 项目），兼容 OpenAI 格式 |
| API 服务 | FastAPI + Uvicorn |
| 数据存储 | SQLite（开发）/ PostgreSQL（生产） |
| 股票数据 | AKShare（A股） |
| 虚拟货币 | CCXT |
| 日志 | structlog + 标准库 logging（JSON 结构化、文件轮转） |
| 测试 | pytest + pytest-asyncio |
| 部署 | Docker + docker-compose |

---

## 目录结构

```
.
├── pyproject.toml              # 项目配置、依赖管理
├── .env.example                # 环境变量模板
├── .gitignore                  # Git 忽略规则
├── README.md                   # 面向人类用户的使用说明
├── AGENTS.md                   # 本文件（开发规范）
├── DEVELOPMENT_LOG.md          # 开发日志（每次变更记录）
│
├── app/                        # 主应用目录
│   ├── __init__.py
│   ├── core/                   # 核心框架层
│   │   ├── config.py           # Pydantic Settings 配置管理
│   │   ├── constants.py        # 项目常量、枚举定义
│   │   ├── exceptions.py       # 业务异常体系
│   │   ├── llm_adapter.py      # LLM 统一调用层（多提供商切换）
│   │   └── logging.py          # 企业级日志系统
│   ├── agents/                 # 智能体定义
│   ├── tools/                  # 工具层（股票/虚拟货币/文件解析等）
│   ├── strategies/             # 交易策略模块
│   │   └── builtin/            # 内置策略
│   ├── memory/                 # 对话历史与上下文压缩
│   ├── data/                   # 数据层
│   │   └── providers/          # 数据提供者
│   ├── api/                    # API 服务层
│   │   └── routers/            # FastAPI 路由
│   └── services/               # 业务服务层
│
├── tests/                      # 测试目录
├── docs/                       # 项目文档
│   ├── system/                 # 系统文档（架构、部署、开发指南）
│   └── business/               # 业务文档（交易策略、业务规则）
├── logs/                       # 运行日志（不纳入版本控制）
├── examples/                   # CLI 输出、示例、临时脚本
│   ├── scripts/                # 临时诊断脚本
│   └── tmp/                    # 一次性临时文件
└── data/                       # 本地数据文件（不纳入版本控制）
```

---

## 安装与构建

```bash
# 安装依赖
pip install -e ".[dev]"

# 或者使用 uv
uv pip install -e ".[dev]"
```

---

## 测试

```bash
# 全量测试
pytest -q

# 带覆盖率
pytest --cov=app --cov-report=term-missing

# 语法检查
python3 -m py_compile app/**/*.py
```

---

## 代码风格与开发约定

### 1. 模块分层约束

新逻辑按职责放入对应模块，禁止跨层直接调用：

| 职责 | 文件 |
|------|------|
| 配置管理 | `app/core/config.py` |
| 日志系统 | `app/core/logging.py` |
| LLM 调用 | `app/core/llm_adapter.py` |
| 异常定义 | `app/core/exceptions.py` |
| 常量定义 | `app/core/constants.py` |

### 2. 异常处理规范

- 所有业务异常必须继承 `AssistantException`
- 异常必须包含 `code` 和 `message`
- 可选 `details` 字典携带额外上下文
- 禁止裸抛 `Exception`，必须使用具体异常类型

### 3. 数据模型

- 配置类使用 Pydantic BaseSettings/BaseModel
- 核心配置使用 `@dataclass(slots=True)`（参考 condex 项目）
- 枚举使用 `StrEnum`（Python 3.11+）

### 4. 字符串与编码

- 统一使用 UTF-8
- JSON 输出默认 `ensure_ascii=False`
- 日志中的中文内容保持原样

### 5. 类型注解

- 全部代码必须使用类型注解
- 使用 `from __future__ import annotations` 支持延迟注解
- 可选类型使用 `X | None` 语法（Python 3.11+）

---

## 开发工作流规范（强制执行）

### 1. 开发前必须说明改动点

**每次编写代码前，必须先向用户说明：**
- 本次改动的目标
- 涉及哪些文件
- 改动的具体方案
- 测试计划

**获得用户明确同意后，才能开始编写代码。**

### 2. 修改必须同步记录

**任何代码或配置的实质性修改完成后，必须同步记录到开发日志。**

| 日志文件 | 记录内容 | 面向读者 |
|---------|---------|---------|
| `DEVELOPMENT_LOG.md` | 改动摘要、决策过程、验证结果、遇到的问题 | 开发团队、未来维护者 |
| `docs/system/CHANGELOG.md` | 版本变更、功能列表、修复列表 | 外部用户、协作者 |

记录时机：
- 新增功能、修复 bug、性能优化、接口变更 → 同步追加
- 涉及方案选型、踩坑、验证过程 → 同步追加

### 3. 文档变更必须同步更新

如果修改涉及以下文档类型，必须同步更新：

| 文档类型 | 存放位置 | 说明 |
|---------|---------|------|
| 系统说明文档 | `docs/system/` | 架构、部署、开发指南 |
| 业务文档 | `docs/business/` | 交易策略、业务规则、术语表 |
| API/接口文档 | `docs/system/API.md` | HTTP API 端点、请求/响应格式 |

**约束**：禁止只改代码不改文档。

### 4. 每一步完成后必须测试

- 每个模块开发完成后，必须编写对应的单元测试
- 测试通过后才能进入下一步
- 测试覆盖率目标：核心业务逻辑 >= 80%

### 5. 提交前必须本地 commit

每轮有意义的改动完成后，**必须先 `git add` + `git commit` 提交到本地**：

- 提交信息遵循 Conventional Commits 规范：
  - `feat:` 新功能
  - `fix:` 修复
  - `docs:` 文档
  - `test:` 测试
  - `refactor:` 重构
  - `chore:` 构建/工具
- 提交信息应清晰描述改动的目的和范围
- 提交前检查：`.env` 是否含敏感信息、临时产物是否被误加入

### 6. 禁止提交的敏感信息

- `.env` 文件（含 API Key、密码等）
- 运行期产物：日志、数据库文件、临时脚本输出
- 个人报告或分析产物

正确做法：
- 敏感配置通过 `.env.example` 模板同步
- 临时产物写入 `examples/` 但不加入 git

---

## 输出规范

### 1. CLI 默认输出目录

所有会产生文件输出的命令，默认写入 `examples/`：

- 查询结果 → `examples/query_YYYYMMDD_HHMMSS.json`
- 分析报告 → `examples/analysis_YYYYMMDD_HHMMSS.json`
- 临时脚本 → `examples/scripts/`

### 2. 已有目录约定

| 目录 | 用途 |
|------|------|
| `logs/` | 运行日志文件 |
| `data/` | 本地数据库、缓存 |
| `examples/` | CLI 输出、报告、示例 |
| `examples/scripts/` | 临时诊断/测试脚本 |
| `examples/tmp/` | 一次性临时文件 |
| `tests/` | pytest 测试文件 |
| `docs/` | 项目文档 |

项目根目录只保留源代码、配置和文档，不保存运行期产物。

---

## 关键配置

### 环境变量

复制 `.env.example` 到 `.env` 后按需填写：

```bash
cp .env.example .env
```

核心配置组：

- **LLM Provider**：`STOCK_ASSISTANT_LLM_PROVIDER`（kimi/xiaomi/openai/deepseek）
- **LLM 配置**：`{PROVIDER}_LLM_API_KEY`、`{PROVIDER}_LLM_MODEL`、`{PROVIDER}_LLM_BASE_URL`
- **日志**：`STOCK_ASSISTANT_LOG_LEVEL`、`STOCK_ASSISTANT_LOG_JSON`
- **数据库**：`STOCK_ASSISTANT_DATABASE_URL`

---

## LLM 集成规范

### 多提供商切换

通过 `app/core/llm_adapter.py` 统一管理：

```python
from app.core.llm_adapter import LlmService

# 从环境变量创建
service = LlmService.from_env()

# 调用 LLM
result = service.chat([
    {"role": "system", "content": "你是一个股票分析师"},
    {"role": "user", "content": "分析贵州茅台"},
])
```

### LangChain 兼容

```python
from app.core.llm_adapter import LangChainLlmAdapter

# 创建 LangChain 兼容的 LLM
llm = LangChainLlmAdapter.from_env()

# 直接用于 LangChain Agent
from langchain.agents import AgentExecutor, create_tool_calling_agent
```

---

## 安全注意事项

1. **密钥管理**：API Key 只通过环境变量或 `.env` 注入，不要写进仓库文件
2. **SQL 注入防护**：所有数据库查询使用参数化绑定
3. **路径安全**：CLI 和 API 接收的路径参数应验证是否在预期目录内
4. **交易安全**：下单功能默认使用模拟模式，真实交易需显式开启
5. **日志脱敏**：日志中禁止输出 API Key、密码等敏感信息

---

## 部署方式

1. **开发模式**：`uvicorn app.api.main:app --reload`
2. **生产模式**：Docker + docker-compose
3. **CLI 模式**：`python -m app.cli`

---

## 版本与变更

- 当前版本：`0.1.0`
- 版本定义在 `pyproject.toml`
- 变更历史见 `DEVELOPMENT_LOG.md` 和 `docs/system/CHANGELOG.md`

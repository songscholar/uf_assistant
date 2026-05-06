# UF Stock Assistant — 开发日志

> 记录每次开发变更、决策过程、验证结果和遇到的问题。

---

## 2026-05-06 — 第一阶段：项目基础架构搭建

### 变更摘要

搭建项目基础骨架，包括目录结构、依赖管理、企业级日志系统、配置管理、LLM 适配层和开发规范文档。

### 新增文件

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | 项目依赖配置，包含 LangChain、FastAPI、AKShare、CCXT、structlog 等 |
| `.env.example` | 环境变量模板，支持 Kimi/Xiaomi/OpenAI/DeepSeek 多提供商配置 |
| `AGENTS.md` | 开发规范文档（代码风格、Git 规范、文档要求、安全事项、LLM 集成规范） |
| `app/core/config.py` | Pydantic Settings 配置管理，支持 `.env` 加载、单例模式 |
| `app/core/constants.py` | 项目常量：市场代码、证券类型、订单状态、策略类型、时间周期等枚举 |
| `app/core/exceptions.py` | 业务异常体系：基类 + 具体异常（LLM/数据/交易/策略/文件/记忆等） |
| `app/core/logging.py` | 企业级日志：JSON 结构化、文件轮转(RotatingFileHandler)、彩色控制台、分级输出 |
| `app/core/llm_adapter.py` | LLM 统一调用层（参考 condex 项目 LlmService）：多提供商切换、LangChain BaseChatModel 兼容适配器 |
| `app/core/__init__.py` | 核心模块统一导出 |
| `tests/test_config.py` | 配置管理单元测试（默认值、单例、环境变量覆盖） |
| `tests/test_logging.py` | 日志系统单元测试（目录创建、日志记录、业务/错误/交易日志） |
| `tests/test_llm_adapter.py` | LLM 适配器单元测试（配置加载、服务初始化、内容提取、工具调用提取） |

### 技术决策

1. **LLM 调用层设计**：参考 condex 项目的 `LlmService` 设计，使用 Python 标准库 `urllib.request` 直接调用 OpenAI-compatible API，而非官方 SDK。这样做的好处是：
   - 零额外依赖（标准库即可）
   - 支持任意 OpenAI-compatible 接口
   - 轻量、可控

2. **LangChain 兼容**：提供 `LangChainLlmAdapter` 继承 `BaseChatModel`，将自研 `LlmService` 包装为 LangChain 接口，可直接用于 Agent 编排。

3. **日志系统**：使用 `structlog` + 标准库 `logging`，支持：
   - 控制台彩色输出（开发友好）
   - 文件 JSON 结构化输出（便于日志采集分析）
   - 按大小轮转，防止日志文件无限增长

4. **配置管理**：使用 `pydantic-settings` 的 `BaseSettings`，支持：
   - `.env` 文件自动加载
   - 嵌套配置（log/database/cache）
   - 环境变量前缀区分
   - 单例缓存 + 热重载

### 验证结果

- ✅ 所有单元测试通过：`pytest -q`（31 个测试用例）
- ✅ 配置加载正常：默认值、环境变量覆盖、单例模式
- ✅ 日志系统正常：目录创建、结构化输出、分级记录
- ✅ LLM 适配器正常：提供商配置加载、内容解析、工具调用解析

### 遇到的问题

无。

### Git 提交

```
feat(phase-1): 初始化项目基础架构 + LLM 适配层

- 创建完整项目目录结构
- 配置 pyproject.toml 依赖管理
- 实现企业级日志系统（JSON结构化、文件轮转、彩色控制台）
- 实现 Pydantic Settings 配置管理
- 参考 condex 项目封装 LLM 统一调用层（多提供商切换）
- 实现 LangChain 兼容的 LLM 适配器
- 建立 AGENTS.md 开发规范
- 编写核心模块单元测试（31个测试用例全部通过）
```

---

## 2026-05-06 — 第二阶段：核心框架层

### 变更摘要

实现 LangChain Agent 骨架、对话历史持久化、上下文自动压缩机制、系统提示词模板。

### 新增文件

| 文件 | 说明 |
|------|------|
| `app/memory/conversation.py` | 对话存储：基于 SQLAlchemy 的会话/消息 CRUD，支持 SQLite 持久化 |
| `app/memory/compressor.py` | 上下文压缩器：阈值触发 + LLM 摘要，支持 fallback 截断策略 |
| `app/memory/manager.py` | 记忆管理器：整合存储与压缩，提供 `get_context()` 统一接口 |
| `app/memory/__init__.py` | 记忆模块导出 |
| `app/agents/prompts.py` | 系统提示词模板：角色定义、场景提示词（分析/策略/选股/市场/交易/虚拟货币） |
| `app/agents/stock_assistant.py` | 股票助手 Agent：基于 LangGraph 的状态机，含 AgentState/agent_node/tool_node/finalize_node |
| `app/agents/__init__.py` | Agent 模块导出 |
| `tests/test_memory.py` | 记忆模块测试（对话存储 9 个用例 + 压缩器 4 个用例 + 管理器 5 个用例） |
| `tests/test_agents.py` | Agent 模块测试（提示词 8 个用例 + Agent 3 个用例 + Graph 2 个用例） |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `app/memory/conversation.py` | 修复时间戳：将 `func.now()` 改为 `datetime.now(timezone.utc)`，解决 SQLite 中时间精度不足导致的排序问题 |

### 技术决策

1. **对话存储**：使用 SQLAlchemy ORM + SQLite，表结构：
   - `conversations`：会话元数据（id, user_id, title, summary, is_compressed）
   - `messages`：消息内容（id, conversation_id, role, content, metadata, created_at）
   - 优点：轻量、无需额外服务、易于迁移到 PostgreSQL

2. **上下文压缩机制**：
   - 阈值：`CONTEXT_COMPRESS_THRESHOLD = 20` 轮消息触发压缩
   - 保留数：`CONTEXT_COMPRESS_TARGET = 10` 轮最近消息
   - 压缩方式：LLM 生成摘要 + 保留最近消息
   - fallback：LLM 不可用时，简单提取股票代码并截断

3. **LangGraph Agent 架构**：
   - State：`messages`, `context`, `tools_called`, `final_answer`, `should_end`
   - 节点：`agent`（LLM 推理）→ `tools`（工具执行）→ `finalize`（结束处理）
   - 条件边：`should_continue` 判断是否有工具调用
   - 优点：状态可视化、可扩展、支持循环工具调用

4. **提示词设计**：
   - 统一角色定义 `STOCK_ASSISTANT_ROLE`
   - 场景化提示词模板（分析/策略/选股/市场/交易/虚拟货币）
   - 支持自定义 system prompt 和补充指令

### 验证结果

- ✅ 所有单元测试通过：`pytest -q`（63 个测试用例，新增 32 个）
- ✅ 对话存储：创建/读取/追加/删除/计数/清空 全部正常
- ✅ 上下文压缩：阈值判断、fallback 压缩、历史格式化 正常
- ✅ 记忆管理器：会话初始化、消息添加、上下文组装、统计 正常
- ✅ Agent 骨架：提示词构建、消息转换、Graph 创建、状态流转 正常

### 遇到的问题

1. **SQLite 时间精度问题**：使用 `func.now()` 时，多条消息在极短时间内插入，时间戳相同导致排序不确定。解决方案：改用 Python 的 `datetime.now(timezone.utc)`，确保微秒级精度。

2. **structlog 日志句柄关闭**：测试中多次调用 `setup_logging()` 导致旧句柄指向关闭的流。不影响功能，仅测试输出中有 warning。

### Git 提交

```
feat(phase-2): 核心框架层 — Agent骨架 + 对话管理 + 上下文压缩

- 实现对话历史持久化（SQLAlchemy + SQLite）
- 实现上下文自动压缩机制（阈值触发 + LLM 摘要）
- 实现记忆管理器（整合存储与压缩）
- 使用 LangGraph 构建股票助手 Agent 骨架
- 定义系统提示词模板
- 编写记忆模块和 Agent 单元测试（63个测试用例全部通过）
```

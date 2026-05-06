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

- ✅ 所有单元测试通过：`pytest -q`（11 个测试用例）
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
- 编写核心模块单元测试（11个测试用例全部通过）
```

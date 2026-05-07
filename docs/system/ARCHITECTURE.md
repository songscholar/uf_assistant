# UF Stock Assistant — 架构设计文档

> 本文档描述系统的整体架构、模块职责、数据流和关键技术决策。

---

## 1. 系统概览

UF Stock Assistant 是一个基于 LangChain + LangGraph 的智能股票助手 Agent，通过 FastAPI 提供 HTTP 服务。系统采用分层架构设计，具备良好的扩展性和可维护性。

### 1.1 核心能力

```
┌─────────────────────────────────────────────────────────────┐
│                     用户交互层                               │
│      (API 客户端 / 前端 / CLI / MCP 客户端 / AI Agent)       │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┴─────────────────┐
            │                                   │
            ▼                                   ▼
┌─────────────────────────────┐     ┌────────────────────────────┐
│  FastAPI 服务层 (人类)       │     │  Agent Gateway (机器)      │
│  ┌─────────┐ ┌─────────┐   │     │  /api/agent/v1/*           │
│  │ 对话路由 │ │股票路由 │   │     │  • Token + Scope 认证      │
│  │交易路由 │ │策略路由 │   │     │  • 速率限制 + 审计日志      │
│  └─────────┘ └─────────┘   │     │  • 异步 Job + Paper Orders │
└─────────────────────────────┘     │  • Idempotency + KillSwitch│
            │                       └────────────────────────────┘
            │                                   │
            └─────────────────┬─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent 编排层                              │
│              LangGraph 状态机 + 提示词工程                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     工具执行层                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │股票数据 │ │虚拟货币 │ │市场数据 │ │文件解析 │  ...     │
│  │(AKShare)│ │(CCXT)   │ │(AKShare)│ │(OCR)    │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     基础设施层                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ LLM 调用│ │数据存储 │ │配置管理 │ │日志系统 │          │
│  │(多厂商) │ │(SQLite) │ │(Pydantic│ │(structlog│          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 模块架构

### 2.1 核心层 (`app/core/`)

| 模块 | 职责 | 关键技术 |
|------|------|---------|
| `config.py` | 配置管理 | Pydantic Settings，`.env` 加载，单例模式 |
| `constants.py` | 项目常量 | StrEnum，市场代码/订单类型/策略类型等 |
| `exceptions.py` | 异常体系 | 分层异常：LLM/数据/交易/策略/文件/记忆 |
| `llm_adapter.py` | LLM 调用层 | 参考 condex 项目，urllib 原生 HTTP，LangChain 兼容 |
| `logging.py` | 日志系统 | structlog + RotatingFileHandler，JSON 结构化 |

**LLM 适配器设计**：

```
环境变量 → LlmProviderConfig → LlmService → LangChainLlmAdapter
                │                      │            │
                ▼                      ▼            ▼
          多提供商配置           统一 chat()     BaseChatModel
          (Kimi/OpenAI/          工具调用支持     Agent 可用
           DeepSeek/Xiaomi)
```

### 2.2 认证层 (`app/auth/`)

| 模块 | 职责 | 关键技术 |
|------|------|---------|
| `models.py` | 用户/验证码/OAuth/安全日志等 9 张表 | SQLAlchemy ORM，单例引擎，`init_auth_tables()` |
| `password.py` | 密码哈希与验证 | bcrypt 12 轮，SHA-256 fallback，强度校验 |
| `jwt_auth.py` | JWT 令牌生成/验证 | PyJWT HS256，7 天过期，token_version 失效机制 |
| `dependencies.py` | FastAPI 认证依赖注入 | `get_current_user`、`require_admin`、`require_permission` |
| `email_service.py` | 邮箱验证码 | 频率限制（1/60s），防暴力破解（5 次锁 30 分钟），SMTP+STARTTLS |
| `security_service.py` | 安全基础设施 | IP 封锁、账户锁定、Turnstile 验证、审计日志 |
| `oauth_service.py` | 第三方登录 | Google + GitHub OAuth 2.0，CSRF state 防护 |
| `user_service.py` | 用户生命周期 | CRUD、认证、积分、VIP、密码管理、管理员自举 |

**认证流程**：

```
登录请求 → IP 频率检查 → 账户锁定检查 → Turnstile 验证
    → 用户名/密码验证 → JWT 生成 → 返回 token + user
```

**RBAC 权限映射**：

```
viewer → [dashboard, view]
user   → [dashboard, view, indicator, backtest, strategy, portfolio]
manager → [...user, settings]
admin  → [...manager, user_manage, credentials]
```

### 2.3 Agent 层 (`app/agents/`)

采用 **LangGraph 状态机** 架构：

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  START  │────▶│  agent  │────▶│should_  │
└─────────┘     │ (LLM)   │     │continue │
                └─────────┘     └────┬────┘
                     ▲               │
                     │    有工具调用   │ 无工具调用
                     │               │
                ┌────┴────┐     ┌────▼────┐
                │  tools  │◀────│ finalize│
                │(执行)   │     │(结束)   │
                └─────────┘     └────┬────┘
                                     │
                                ┌────▼────┐
                                │   END   │
                                └─────────┘
```

- **State**: `messages`, `context`, `tools_called`, `final_answer`, `should_end`
- **节点**: `agent_node`（推理）、`tool_node`（工具执行）、`finalize_node`（结束处理）
- **提示词**: 6 大场景模板（分析/策略/选股/市场/交易/虚拟货币）

### 2.3 工具层 (`app/tools/`)

| 工具模块 | 数据源 | 功能 |
|---------|--------|------|
| `stock_data.py` | AKShare | 搜索/信息/实时行情/历史K线/财务/资金流向 |
| `crypto_data.py` | CCXT (Binance) | 价格/行情/K线/市值排行 |
| `market.py` | AKShare | 指数/板块/龙虎榜/北向资金 |
| `file_parser.py` | unstructured/PIL | PDF/DOCX/XLSX/TXT/图片OCR |
| `trading.py` | 内存模拟 | 下单/持仓/订单/投资组合 |

**设计原则**：
- 懒加载外部库（`_get_ak()`），避免启动时初始化
- 统一返回 JSON 字符串，便于 LLM 消费
- 异常封装为具体业务异常

### 2.4 策略层 (`app/strategies/`)

支持双范式策略引擎：

```
┌─────────────────────────────────────────────────────────────────┐
│                    策略引擎（双范式）                              │
├─────────────────────────────────────────────────────────────────┤
│  evaluate 模式（传统）        │  IndicatorStrategy（指标代码）    │
│  BaseStrategy → 4 个内置策略  │  df['buy']/df['sell'] 数据帧    │
│  MA/MACD/RSI/Bollinger       │  @param 参数 + @strategy 风控    │
├─────────────────────────────────────────────────────────────────┤
│  ScriptStrategy（事件驱动）   │  回测引擎（BacktestService）      │
│  on_bar(ctx, bar) 脚本       │  SL/TP/追踪止损/仓位管理          │
│  ctx.buy()/ctx.sell()        │  多时间框架 / 夏普 / 最大回撤     │
├─────────────────────────────────────────────────────────────────┤
│  实盘执行器（TradingExecutor）│  交易所适配（ExchangeClient）     │
│  守护线程/策略               │  CCXT（9 个交易所）               │
│  信号队列 + 服务端风控       │  SimulatedStockClient（A 股）     │
├─────────────────────────────────────────────────────────────────┤
│  辅助模块                                                     │
│  PendingOrderWorker │ PortfolioMonitor │ NotifierManager        │
│  挂单执行            │ 持仓监控           │ 信号通知             │
└─────────────────────────────────────────────────────────────────┘
```

**策略注册表**：
- `StrategyRegistry`：管理 evaluate 模式策略（MA/MACD/RSI/Bollinger）
- `IndicatorCodeRegistry`：管理指标代码（name, code, @param, @strategy）
- 单例模式，支持 key 和中文名称映射

**安全沙箱**（`app/core/safe_exec.py`）：
- 白名单 builtins（~50 个安全函数）
- 受限 import（仅 numpy/pandas/math/json/datetime 等）
- AST + regex 双重安全检查（~40 个危险模式）
- 超时控制（SIGALRM + threading.Timer）

### 2.5 记忆层 (`app/memory/`)

```
用户输入 → ConversationStore (SQLite) → 消息计数检查
                                              │
                    超过阈值 (20轮) ◀──────────┘
                          │
                          ▼
              ContextCompressor (LLM 摘要)
                          │
                          ▼
              保存摘要 + 保留最近 10 轮
```

- **ConversationStore**: SQLAlchemy ORM，会话/消息 CRUD
- **ContextCompressor**: 阈值触发，LLM 生成摘要，fallback 截断
- **MemoryManager**: 整合存储与压缩，提供 `get_context()` 统一接口

### 2.6 服务层 (`app/services/`)

| 服务 | 职责 |
|------|------|
| `stock_picker.py` | 策略选股、快速筛选（排除 ST） |
| `market_analyzer.py` | 日报生成、板块轮动、风险等级评估 |
| `analysis_memory.py` | AI 分析记忆存储、历史验证、相似模式匹配、用户反馈 |
| `ai_calibration.py` | 离线阈值校准：Grid Search 最优 BUY/SELL/HOLD 决策边界 |
| `reflection.py` | 后台反射 Worker：定期验证旧决策 → 触发校准 |
| `billing.py` | 积分扣减、会员管理、USDT 支付对账 |

### 2.7 API 层 (`app/api/`)

**人类面向路由** (`app/api/routers/`)

| 路由模块 | 端点数 | 功能 |
|---------|--------|------|
| `chat.py` | 5 | 对话/会话管理 |
| `stock.py` | 6 | 股票数据查询 |
| `market.py` | 5 | 市场数据查询 |
| `crypto.py` | 4 | 虚拟货币查询 |
| `trading.py` | 5 | 模拟交易操作 |
| `strategy.py` | 5 | 策略执行/选股/自定义 |
| `upload.py` | 2 | 文件上传/解析 |
| `billing.py` | 8 | 计费/会员/USDT 支付 |
| `analysis.py` | 6 | AI 分析记忆（历史/统计/反馈/校准配置） |

**Agent Gateway** (`app/api/agent/`)

| 路由模块 | 端点数 | Scope | 功能 |
|---------|--------|-------|------|
| `markets.py` | 8 | R | 股票搜索/实时/历史、市场概况/指数/板块、加密货币 |
| `chat.py` | 2 | R | 对话 + SSE 流式（支持断点续传） |
| `strategies.py` | 4 | R/B | 策略列表、异步执行（返回 job_id）、选股、筛选 |
| `backtests.py` | 1 | B | 提交异步回测任务（复用 BacktestService，返回 job_id） |
| `trading.py` | 7 | R/T | 持仓/订单查询、下单（paper-only）、Kill Switch、Paper Orders |
| `__init__.py` | 8 | R/C | whoami、admin token CRUD、jobs 查询 |

**Agent Gateway 安全设计**：
- Token 认证：`Authorization: Bearer uf_agent_xxx`
- Scope 权限：R(读) / W(写策略) / B(回测) / N(通知) / C(凭证管理) / T(交易)
- 白名单：markets / instruments 细粒度控制
- 速率限制：每 token 每分钟，返回 `X-RateLimit-*` 头
- 审计日志：每次调用记录 route/scope/status/duration，自动脱敏
- 幂等性：`Idempotency-Key` header 防止重复提交
- Paper-only：默认模拟交易，实盘需 token + 服务端双重开关
- SaaS guard：`UF_ASSISTANT_DEPLOYMENT_MODE=saas` 自动拒绝 T scope

---

## 3. 数据流

### 3.1 对话流程

```
用户输入
    │
    ▼
MemoryManager.get_context() ──▶ 获取历史上下文
    │                              │
    ▼                              │
Agent.chat()                      │
    │                              │
    ├──▶ LangGraph 状态机          │
    │       │                      │
    │       ├──▶ LLM 推理          │
    │       │       │              │
    │       │       ├──▶ 需要工具? ──▶ 工具调用 ──▶ 返回结果 ──▶ 继续推理
    │       │       │              │
    │       │       └──▶ 直接回答  │
    │       │                      │
    │       └──▶ finalize_node     │
    │                              │
    └──▶ 保存助手回复到记忆 ◀──────┘
                │
                ▼
           返回给用户
```

### 3.2 策略选股流程

```
用户选择策略 + 股票列表
        │
        ▼
StockPicker.pick_by_strategy()
        │
        ├──▶ 遍历股票列表
        │       │
        │       ├──▶ 获取历史数据 (AKShare)
        │       │
        │       ├──▶ Strategy.evaluate()
        │       │       │
        │       │       ├──▶ pandas 计算指标
        │       │       │
        │       │       └──▶ 生成 Signal
        │       │
        │       └──▶ 记录结果
        │
        ├──▶ 按置信度排序
        │
        └──▶ 返回买卖信号列表
```

### 3.3 回测流程

```
用户提交指标代码 + 参数
        │
        ▼
BacktestService.run()
        │
        ├──▶ _fetch_kline_data() ──▶ AKShare / CCXT ──▶ 内存缓存 (TTL+LRU)
        │
        ├──▶ _execute_indicator() ──▶ safe_exec_code()
        │       │                           │
        │       │                           ├──▶ 白名单 builtins
        │       │                           ├──▶ AST + regex 安全检查
        │       │                           └──▶ 60s 超时
        │       │
        │       └──▶ df['buy'] / df['sell'] / df['open_long'] ...
        │
        ├──▶ _simulate_trading()
        │       │
        │       ├──▶ 4-way 信号解析（open_long/close_long/open_short/close_short）
        │       │
        │       ├──▶ 仓位管理（trendAdd / dcaAdd / trendReduce / adverseReduce）
        │       │
        │       ├──▶ 风控检查（SL / TP / trailing_stop）
        │       │
        │       └──▶ 生成 equity_curve + trades[]
        │
        ├──▶ _calculate_metrics()
        │       │
        │       ├──▶ Sharpe / Sortino / max_drawdown
        │       ├──▶ profit_factor / win_rate / CAGR
        │       └──▶ calmar_ratio / volatility
        │
        ├──▶ _persist_backtest_run()
        │       │
        │       └──▶ SQLite: backtest_runs / backtest_trades / backtest_equity_points
        │
        └──▶ 返回 JSON（含 equity_curve 采样点、逐笔交易、绩效指标）
```

**Agent Gateway 回测**（`POST /api/agent/v1/backtests`）：
- 复用相同的 `BacktestService.run()`，结果与人类 UI 一致
- 通过 `submit_job()` 放入异步队列，返回 `job_id`
- 支持 `Idempotency-Key` 防止重复提交

### 3.4 AI 分析记忆与反射校准流程

```
Agent 产生分析结果
        │
        ▼
AnalysisMemoryService.store()
        │
        ├──▶ 解析 consensus / scores / indicators / reasons
        │
        └──▶ INSERT analysis_memory (user_id, market, symbol, decision, ...)
        │
        ▼
用户查看历史 ──▶ GET /api/v1/analysis/history
用户反馈质量 ──▶ POST /api/v1/analysis/feedback
相似模式比对 ──▶ GET /api/v1/analysis/similar/{market}/{symbol}


后台 Reflection Worker（每日 / 可配置间隔）
        │
        ▼
ReflectionService.run_verification_cycle()
        │
        ├──▶ 拉取 N 天前未验证记录
        │       │
        │       ├──▶ get_current_price() ──▶ AKShare / CCXT
        │       │
        │       ├──▶ 计算 actual_return_pct
        │       │
        │       └──▶ UPDATE validated_at / was_correct
        │
        └──▶ 样本充足? ──▶ AICalibrationService.calibrate_market()
                │
                ├──▶ Grid Search 候选阈值 [10, 12, ..., 30]
                │
                ├──▶ 对每个阈值：预测决策 vs 实际收益 → 准确率
                │
                ├──▶ Tie-break：优先更高 BUY+SELL 覆盖率
                │
                └──▶ INSERT ai_calibration (buy_threshold, sell_threshold, ...)
                        │
                        ▼
                后续分析复用最新阈值 ──▶ AICalibrationService.get_latest(market)
```

**校准规则**：
- BUY 正确：actual_return_pct > +2%
- SELL 正确：actual_return_pct < -2%
- HOLD 正确：|actual_return_pct| ≤ 5%
- 默认阈值：BUY ≥ 20, SELL ≤ -20, min_consensus_abs = 15
- 前端/Agent 轮询 `/api/agent/v1/jobs/{job_id}` 获取结果

---

## 4. 关键技术决策

### 4.1 为什么使用 urllib 而不是官方 SDK？

参考 condex 项目的设计，使用 Python 标准库 `urllib.request` 直接调用 OpenAI-compatible API：

- **零额外依赖**：不需要安装 `openai` 或 `anthropic` 包
- **通用性**：支持任意 OpenAI-compatible 接口（Kimi/DeepSeek/自定义）
- **轻量可控**：代码透明，便于调试和扩展

通过 `LangChainLlmAdapter` 包装为 `BaseChatModel`，无缝接入 LangChain 生态。

### 4.2 为什么选择 SQLite？

- **开发友好**：零配置，单文件存储
- **足够轻量**：对话历史数据量不大
- **易于迁移**：SQLAlchemy 抽象层，可无缝切换 PostgreSQL

### 4.3 上下文压缩机制

当对话消息数超过 `CONTEXT_COMPRESS_THRESHOLD` (20轮) 时：

1. 提取历史对话（排除 system 消息）
2. 调用 LLM 生成摘要（保留关键的股票代码、交易决策、策略名称）
3. 保存摘要到会话，清空旧消息
4. 保留最近 `CONTEXT_COMPRESS_TARGET` (10轮) 完整对话

**fallback**：LLM 不可用时，提取股票代码并简单截断。

### 4.4 模拟交易设计

采用内存存储的 `MockTradingBackend`：

- **立即成交**：订单提交后立即状态变为 FILLED
- **持仓计算**：买入更新平均成本，卖出计算实现盈亏
- **盈亏统计**：支持未实现盈亏和已实现盈亏

生产环境可替换为真实券商 API 适配器。

---

## 5. 扩展性设计

### 5.1 添加新数据源

1. 在 `app/data/providers/` 创建新提供者
2. 在 `app/tools/` 创建对应工具函数
3. 在 `app/tools/__init__.py` 的 `ALL_TOOLS` 中注册

### 5.2 添加新策略

1. 继承 `BaseStrategy`
2. 实现 `name`, `description`, `parameters`, `evaluate`
3. 在 `app/strategies/registry.py` 的 `_BUILTIN_STRATEGIES` 中注册

### 5.3 添加新 API 接口

1. 在 `app/api/routers/` 创建新路由模块
2. 在 `app/api/main.py` 中 `app.include_router()` 注册

### 5.4 添加新 LLM 提供商

1. 在 `app/core/llm_adapter.py` 的 `_PROVIDER_ENV_PREFIXES` 添加前缀
2. 在 `_PROVIDER_DEFAULT_MODELS` 添加默认模型
3. 配置对应的环境变量即可使用

---

## 6. 安全考虑

| 层面 | 措施 |
|------|------|
| API Key | 只通过 `.env` 注入，不提交到仓库 |
| SQL 注入 | 所有查询使用 SQLAlchemy ORM，参数化绑定 |
| 文件上传 | 临时文件存储，解析后立即删除 |
| 自定义策略 | 禁止危险操作（eval/exec/import os/subprocess） |
| 日志脱敏 | 禁止输出 API Key、密码等敏感信息 |
| 模拟交易 | 默认模拟模式，真实交易需显式开启 |

---

## 7. 部署建议

### 7.1 开发环境

```bash
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 7.2 生产环境

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

或使用 Gunicorn + Uvicorn worker：

```bash
gunicorn app.api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 7.3 Docker（可选）

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e "."
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 8. 监控与运维

### 8.1 日志

- 控制台：彩色输出，开发友好
- 文件：`logs/assistant.log`，JSON 结构化，按大小轮转（10MB × 10 份）
- 关键事件：llm_chat、tool_invocation、order_submitted、compression_triggered

### 8.2 健康检查

```http
GET /health
```

返回：状态、版本号、时间戳

### 8.3 性能指标

- 请求耗时：中间件自动记录（duration_ms）
- LLM 延迟：`llm_chat_completed` 事件记录 latency_ms
- 工具调用：`tool_invocation` 事件记录执行结果

---

## 9. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.1.0 | 2026-05-06 | 初始版本，完成核心功能 |
| 0.1.0 | 2026-05-06 | 回测引擎迁移（QuantDinger → UF Stock Assistant） |
| 0.1.0 | 2026-05-06 | Agent Gateway 回测端点补充（`POST /api/agent/v1/backtests`） |

# Changelog

## [0.1.0] — 2026-05-07

### Added
- **计费与商业化系统**（新模块）
  - 积分系统：功能按次扣费、积分充值/赠送、变动日志分页查询
  - 会员系统：月付/年付/终身会员，支持叠加与按月发放
  - USDT-TRC20 支付：每单独立地址、TronGrid 自动对账、后台 Worker 轮询
  - 计费 API：`/api/v1/billing/plans`, `/credits`, `/credits/log`, `/usdt/create`, `/usdt/order/{id}`
  - 管理 API：积分调整、VIP 设置
  - 计费业务文档：`docs/business/BILLING.md`
  - 计费模块单元测试：15 个用例

- **Agent Gateway + MCP Server**（完整实现，参考 QuantDinger 设计）
  - Agent Token 认证：SHA-256 哈希存储、6 个 Scope（R/W/B/N/C/T）、markets/instruments 白名单
  - 速率限制：内存滑动窗口 + `X-RateLimit-Limit/Remaining/Reset` 响应头
  - Token 状态生命周期：active / inactive / revoked，支持 `last_used_at` 追踪
  - 异步 Job 系统：`agent_jobs` 持久化表，策略执行返回 job_id，支持断点续传
  - Paper Orders 表：`agent_paper_orders` 独立记录模拟交易明细
  - 幂等性：`Idempotency-Key` header，W/B/T 端点支持重复请求防护
  - SaaS 部署 guard：`UF_ASSISTANT_DEPLOYMENT_MODE=saas` 自动拒绝 T scope + 强制 paper_only
  - Kill Switch：`POST /trading/kill-switch` 一键取消未成交 paper orders
  - SSE 断点续传：`Last-Event-ID` header + `?since` query param
  - 审计日志自动脱敏：password/secret/token/api_key 等敏感字段自动 redact
  - 统一错误格式：`{code, message, details, retriable}`
  - Admin 端点：Token 列表/吊销/激活/停用（需 C scope）
  - OpenAPI 3.0 规范：`docs/agent/agent-openapi.json`
  - MCP Server：`mcp_server/` 独立包，stdio/sse/streamable-http 传输，只暴露 R/B 类工具

- **AI 分析记忆与反射校准系统（迁移自 QuantDinger）**
  - 分析记忆：`analysis_memory` 表存储每次 AI 决策（decision / confidence / consensus / indicators / reasons）
  - 历史验证：后台 Worker 定期拉取旧记录，对比当前价格计算实际收益率，标记 was_correct
  - 相似模式：基于 RSI / MACD / MA / 波动率加权相似度，检索历史同类技术指标模式
  - 用户反馈：支持 helpful / not_helpful / accurate / inaccurate 反馈，用于质量评估
  - 离线校准：Grid Search 最优 BUY/SELL/HOLD 阈值（候选 10~30），按准确率排序，Tie-break 优先覆盖
  - 阈值默认：BUY ≥ 20, SELL ≤ -20, min_consensus_abs = 15, quality_hold = 0.7
  - 反射 Worker：可配置间隔（默认 86400s），验证 + 条件触发校准
  - API 端点：`/api/v1/analysis/history`, `/stats`, `/feedback`, `/similar`, `/calibration/{market}`
  - 单元测试：10 个用例覆盖存储、查询、反馈、校准、阈值预测

- **原生交易所客户端（完整迁移自 QuantDinger）**
  - 12 个交易所原生 REST 客户端（非 CCXT 封装），共 ~7,300 行交易所特有逻辑
  - Binance（Futures + Spot）：broker ID、hedge mode、时间同步、filter 缓存（LOT_SIZE/PRICE_FILTER/MARKET_LOT_SIZE）
  - OKX：broker_code、simulated_trading header、合约数量转换（ctVal）
  - Bybit：broker_referer、hedge_mode、recv_window、时间同步重试
  - Bitget（Mix + Spot）：channel_api_code、hedge_mode、合约转换、feeDetail 解析
  - Gate（Spot + Futures）：channel_id、quanto_multiplier 合约单位转换
  - KuCoin（Spot + Futures）：API v2 签名、合约乘数（multiplier）、dealSize 转换
  - Coinbase Exchange：sandbox、Base64(HMAC-SHA256) 签名
  - Kraken（Spot + Futures）：XBT↔BTC 映射、userref、PF_ 前缀合约
  - HTX：broker_id、统一账户检测、双 URL（spot/futures）
  - Deepcoin：ISO 8601 时间、appid
  - 基础设施：`BaseRestClient`（统一 REST）、`create_client` 工厂、`symbol` 标准化、`records` 持仓快照、`execution` 信号分发
  - IBKR / MT5 支持：lazy import，本机 TWS/Gateway / MT5 终端连接

- **策略服务增强（迁移自 QuantDinger）**
  - `batch_create_strategies()`：批量创建策略 + group_id 分组，支持多 symbol 同时创建
  - `get_exchange_symbols()`：按交易所获取交易对，支持直接 REST / CCXT fallback / IBKR / MT5
  - `_compute_runtime_metrics()`：策略运行时指标（已实现 PnL / 未实现 PnL / 权益）
  - `_build_bot_display()`：网格/马丁/趋势/DCA bot 的前端展示配置
  - `exchange_execution.py`：凭据解析（credential_id → 查 DB 取 API Key），支持 demo/testnet 检测
  - 新增端点：`POST /strategies/batch`、`POST /strategies/exchange-symbols`、`GET /strategies/{id}/runtime-metrics`

- **回测引擎（完整迁移自 QuantDinger）**
  - `BacktestService`：K 线缓存（TTL+LRU）、指标执行、交易模拟、绩效计算
  - 双范式策略回测：Indicator 模式（df['buy']/df['sell']）+ Script 模式（on_bar 事件驱动）
  - 多时间框架回测：信号在粗粒度生成，执行在细粒度（1m/5m）进行
  - 风险控制：止损/止盈/追踪止损、仓位缩放（trendAdd/dcaAdd/trendReduce/adverseReduce）
  - 绩效指标：Sharpe、max drawdown、profit factor、win rate、CAGR、Sortino
  - 数据持久化：`backtest_runs` / `backtest_trades` / `backtest_equity_points`
  - 安全沙箱：用户指标代码通过 `safe_exec_code` 运行，60s 超时，禁止危险操作
  - 人类 API：`POST /api/v1/strategies/backtest`
  - Agent Gateway API：`POST /api/agent/v1/backtests`（异步 Job，class B scope）
  - 辅助端点：代码验证、质量评分、参数解析、指标执行
  - 回测模型：StrategyModel / IndicatorModel / BacktestRun / BacktestTrade / BacktestEquityPoint

### Changed
- `app/core/config.py`：新增 BillingSettings、MembershipSettings、UsdtPaymentSettings、AgentSettings.deployment_mode、ReflectionSettings
- `app/core/exceptions.py`：新增 BillingError、InsufficientCreditsError、UsdtPaymentError
- `app/api/main.py`：注册 billing/analysis 路由，lifespan 启动/停止 UsdtOrderWorker 与 Reflection Worker，Agent Gateway 响应头注入中间件
- `app/core/constants.py`：新增 AgentScope.NOTIFY、AgentScope.CREDENTIALS、AgentTokenStatus
- `app/memory/`：新增 agent_models.py（agent_tokens / agent_jobs / agent_paper_orders ORM 模型）

### Security
- 计费/USDT 支付默认关闭，需显式开启
- USDT 使用仅观察权限的 xpub，私钥不触碰服务器
- 积分扣减前强制校验余额，防止透支
- Agent Gateway 交易默认 paper-only，实盘需 token + 服务端双重开关
- SaaS 模式下自动拒绝 T scope，防止多租户场景下 agent 实盘交易
- MCP Server  intentionally 不暴露交易工具，安全边界留在 Gateway

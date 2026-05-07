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

### Changed
- `app/core/config.py`：新增 BillingSettings、MembershipSettings、UsdtPaymentSettings、AgentSettings.deployment_mode
- `app/core/exceptions.py`：新增 BillingError、InsufficientCreditsError、UsdtPaymentError
- `app/api/main.py`：注册 billing 路由，lifespan 启动/停止 UsdtOrderWorker，Agent Gateway 响应头注入中间件
- `app/core/constants.py`：新增 AgentScope.NOTIFY、AgentScope.CREDENTIALS、AgentTokenStatus
- `app/memory/`：新增 agent_models.py（agent_tokens / agent_jobs / agent_paper_orders ORM 模型）

### Security
- 计费/USDT 支付默认关闭，需显式开启
- USDT 使用仅观察权限的 xpub，私钥不触碰服务器
- 积分扣减前强制校验余额，防止透支
- Agent Gateway 交易默认 paper-only，实盘需 token + 服务端双重开关
- SaaS 模式下自动拒绝 T scope，防止多租户场景下 agent 实盘交易
- MCP Server  intentionally 不暴露交易工具，安全边界留在 Gateway

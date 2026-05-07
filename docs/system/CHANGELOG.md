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

### Changed
- `app/core/config.py`：新增 BillingSettings、MembershipSettings、UsdtPaymentSettings
- `app/core/exceptions.py`：新增 BillingError、InsufficientCreditsError、UsdtPaymentError
- `app/api/main.py`：注册 billing 路由，lifespan 启动/停止 UsdtOrderWorker
- `.env.example`：新增计费、会员、USDT 支付环境变量模板

### Security
- 计费/USDT 支付默认关闭，需显式开启
- USDT 使用仅观察权限的 xpub，私钥不触碰服务器
- 积分扣减前强制校验余额，防止透支

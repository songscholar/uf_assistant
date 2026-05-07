# UF Stock Assistant — 计费与商业化系统

> 本文档描述计费系统的业务规则、数据模型、API 接口和运营流程。

---

## 1. 系统概述

计费系统为 UF Stock Assistant 提供商业化能力，包括：

- **积分系统**：功能按次扣费、积分充值/赠送、变动日志
- **会员系统**：月付/年付/终身会员，绑定积分额度
- **USDT-TRC20 支付**：链上支付，TronGrid 自动对账

**默认状态**：全部关闭。通过环境变量显式开启。

---

## 2. 业务规则

### 2.1 积分计费

| 功能 | 默认消耗积分 | 说明 |
|------|-------------|------|
| AI 分析 | 10 | 每次调用 LLM 分析 |
| AI 代码生成 | 30 | 每次策略/指标代码生成 |

**规则**：
- `BILLING_ENABLED=false` 时，所有功能免费
- 消耗为 0 的功能免费
- 积分不足时拒绝服务，返回 `INSUFFICIENT_CREDITS` 错误
- 每次扣费记录到 `credits_log` 表
- **幂等去重**：`check_and_consume` 传入非空 `reference_id` 时，同一 `user_id + reference_id` 的扣费只执行一次，防止网络重试导致重复扣费

### 2.2 会员套餐

| 套餐 | 价格(USD) | 赠送积分 | 有效期 |
|------|----------|---------|--------|
| 月付 | 19.9 | 500 | 30 天 |
| 年付 | 199 | 8000 | 365 天 |
| 终身 | 499 | 800/月 | 100 年（按月发放） |

**规则**：
- 月付/年付支持**叠加**：新购买时从当前 VIP 过期时间往后延长
- 终身会员首次立即发放首月积分，之后每 30 天自动发放
- 会员购买记录到 `credits_log` 表

### 2.3 USDT-TRC20 支付

**流程**：
1. 用户选择套餐 → 调用 `/api/v1/billing/usdt/create`
2. 系统从 xpub 派生**独立收款地址**（每单一个地址）
3. 用户向该地址转账对应 USDT 金额
4. 后台 Worker 每 30 秒轮询 TronGrid 检查到账
5. 匹配到转账后，订单状态变为 `paid` → 等待确认秒数 → `confirmed`
6. 确认后自动调用 `purchase_membership` 激活会员并发放积分

**安全规则**：
- 订单 30 分钟未支付自动过期
- 链上匹配要求：目标地址 + 金额 ≥ 订单金额 × 95% + 区块时间 ≥ 订单创建时间（允许 5% 容差，覆盖 dust 差异）
- 幂等确认：已确认的订单不会重复激活会员

---

## 3. 数据模型

### 3.1 user_credits（用户积分表）

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string PK | 用户标识（与对话系统 user_id 一致） |
| credits | decimal(20,2) | 积分余额 |
| vip_expires_at | datetime | VIP 过期时间 |
| vip_plan | string | 当前套餐 monthly/yearly/lifetime |
| vip_is_lifetime | boolean | 是否终身会员 |
| vip_monthly_credits_last_grant | datetime | 终身会员上次发积分时间 |

### 3.2 membership_orders（会员订单表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | 自增主键 |
| user_id | string | 用户标识 |
| plan | string | 套餐类型 |
| price_usd | decimal(10,2) | 支付金额（USD） |
| status | string | 状态（默认 paid） |
| created_at | datetime | 创建时间 |
| paid_at | datetime | 支付/确认时间 |

### 3.3 credits_log（积分日志表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | 自增 |
| user_id | string | 用户标识 |
| action | string | 操作类型：consume/recharge/admin_adjust/membership_bonus/... |
| amount | decimal(20,2) | 变动金额（负数为扣减） |
| balance_after | decimal(20,2) | 变动后余额 |
| feature | string | 功能名（consume 时） |
| reference_id | string | 关联 ID（订单号等） |
| remark | text | 备注 |
| operator_id | string | 操作人标识 |
| created_at | datetime | 记录时间 |

### 3.4 usdt_orders（USDT 订单表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | 自增 |
| user_id | string | 用户标识 |
| plan | string | 套餐类型 |
| chain | string | 链类型（默认 TRC20） |
| amount_usdt | decimal(20,6) | 支付金额 |
| address_index | int | 派生地址索引 |
| address | string | TRC20 收款地址 |
| status | string | pending/paid/confirmed/expired |
| tx_hash | string | 链上交易哈希 |
| paid_at | datetime | 标记 paid 时间 |
| confirmed_at | datetime | 标记 confirmed 时间 |
| expires_at | datetime | 订单过期时间 |

---

## 4. API 接口

### 4.1 查询接口

#### GET /api/v1/billing/plans
获取会员套餐配置 + 当前用户计费快照。

**Headers**：`user-id: default`

**响应**：
```json
{
  "code": "success",
  "data": {
    "plans": { "monthly": {...}, "yearly": {...}, "lifetime": {...} },
    "billing": { "credits": 100, "is_vip": false, "vip_expires_at": null }
  }
}
```

#### GET /api/v1/billing/credits
获取用户积分与 VIP 状态。

#### GET /api/v1/billing/credits/log
获取积分变动日志。

**Query**：`page`, `page_size`

### 4.2 管理接口（需 X-Admin-Key 认证）

所有管理接口需要在 Header 中携带 `X-Admin-Key`，值等于 `.env` 中的 `STOCK_ASSISTANT_BILLING_ADMIN_API_KEY`。
- 未配置 `ADMIN_API_KEY` → 返回 `503 admin_api_key_not_configured`
- Key 不匹配 → 返回 `401 invalid_admin_key`

#### POST /api/v1/billing/credits/add
增加用户积分。

**Headers**：`X-Admin-Key: your-key`
**Body**：`{ user_id, amount, remark }`

#### POST /api/v1/billing/credits/set
设置用户积分（覆盖）。

**Headers**：`X-Admin-Key: your-key`
**Body**：`{ user_id, amount, remark }`

#### POST /api/v1/billing/vip/set
设置 VIP 状态。

**Headers**：`X-Admin-Key: your-key`
**Body**：`{ user_id, expires_at, remark }`

### 4.3 USDT 支付接口

#### POST /api/v1/billing/usdt/create
创建 USDT 支付订单。

**Body**：`{ plan: "monthly" }`

**响应**：
```json
{
  "code": "success",
  "data": {
    "order_id": 1,
    "plan": "monthly",
    "amount_usdt": "19.9",
    "address": "T...",
    "expires_at": "2026-05-07T11:00:00+08:00"
  }
}
```

#### GET /api/v1/billing/usdt/order/{order_id}
查询订单状态（默认刷新链上状态）。

**Query**：`refresh=true|false`

---

## 5. 配置说明

在 `.env` 中配置：

```env
# 计费开关
STOCK_ASSISTANT_BILLING_ENABLED=true
STOCK_ASSISTANT_BILLING_COST_AI_ANALYSIS=10
STOCK_ASSISTANT_BILLING_COST_AI_CODE_GEN=30

# 会员价格
STOCK_ASSISTANT_MEMBERSHIP_MONTHLY_PRICE_USD=19.9
STOCK_ASSISTANT_MEMBERSHIP_YEARLY_PRICE_USD=199
STOCK_ASSISTANT_MEMBERSHIP_LIFETIME_PRICE_USD=499

# USDT 支付（需安装 bip_utils，配置 xpub 和 TronGrid API Key）
STOCK_ASSISTANT_USDT_PAY_ENABLED=true
STOCK_ASSISTANT_USDT_TRC20_XPUB=your-xpub-here
STOCK_ASSISTANT_USDT_TRONGRID_API_KEY=your-key-here

# USDT 调试（启用后将对账日志写入文件，便于排查链上匹配问题）
STOCK_ASSISTANT_USDT_DEBUG_RECONCILE_LOG=true

# 管理接口 API Key（X-Admin-Key 校验用，留空则管理接口返回 503）
STOCK_ASSISTANT_BILLING_ADMIN_API_KEY=change-me-in-production
```

---

## 6. 运营流程

### 开启计费
1. 设置 `STOCK_ASSISTANT_BILLING_ENABLED=true`
2. 配置各功能消耗积分
3. 为用户手动充值初始积分（管理接口）或发放注册赠送积分

### 开启 USDT 支付
1. 安装依赖：`pip install bip_utils requests`
2. 生成或导入 TRON 钱包 xpub（仅观察权限）
3. 配置 `STOCK_ASSISTANT_USDT_TRC20_XPUB`
4. 申请 TronGrid API Key 并配置
5. 设置 `STOCK_ASSISTANT_USDT_PAY_ENABLED=true`
6. 重启服务，Worker 自动启动轮询

### 关闭计费
- 设置 `STOCK_ASSISTANT_BILLING_ENABLED=false`，所有功能立即免费
- USDT 支付保持运行但不再创建新订单

---

## 7. 安全与风控

1. **默认关闭**：所有商业化功能默认关闭，防止误开启
2. **管理接口认证**：`/credits/add`、`/credits/set`、`/vip/set` 需 `X-Admin-Key`，未配置则不可用
3. **积分非负**：set_credits 拒绝负数，扣费前检查余额
4. **扣费幂等**：同一 `reference_id` 的扣费只执行一次，防止网络重试导致重复扣费
5. **USDT 地址隔离**：每单独立地址，防止混淆和重放
6. **USDT 金额容差**：链上匹配允许 5% 容差，覆盖 dust 差异和小幅波动
7. **幂等确认**：已确认订单不会重复激活会员
8. **订单过期**：30 分钟未支付自动过期，防止地址长期被占
9. **xpub 安全**：仅使用观察钱包 xpub，私钥不触碰服务器

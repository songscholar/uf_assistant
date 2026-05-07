# UF Stock Assistant — API 接口文档

> 本文档记录 HTTP API 端点的请求/响应格式。OpenAPI 3.0 规范见 `docs/agent/agent-openapi.json`（Agent Gateway）。

---

## 凭证管理（Credentials）

基路径：`/api/v1/credentials`

### 列出凭证

```
GET /api/v1/credentials
```

**响应**：
```json
{
  "credentials": [
    {
      "id": "cred-001",
      "market": "crypto",
      "name": "Gate.io 主账户",
      "api_key_hint": "abcd...1234",
      "is_active": true
    }
  ]
}
```

### 添加凭证

```
POST /api/v1/credentials
```

**请求体**：
```json
{
  "market": "crypto",
  "name": "Gate.io 主账户",
  "api_key": "...",
  "api_secret": "...",
  "passphrase": "...",
  "extra_config": {"exchange": "gate"}
}
```

**说明**：`market` 取值 `crypto` / `a_share` / `us_stock` / `ibkr` / `mt5`。IBKR/MT5 的详细配置通过 `extra_config` 传递：

- **IBKR**：`{"ibkr_host": "127.0.0.1", "ibkr_port": 7497, "ibkr_client_id": 1}`
- **MT5**：`{"mt5_login": "12345", "mt5_password": "...", "mt5_server": "ICMarkets-Demo"}`

### 更新凭证

```
PUT /api/v1/credentials/{credential_id}
```

**请求体**：`CredentialUpdateRequest`（字段均为可选）

### 删除凭证

```
DELETE /api/v1/credentials/{credential_id}
```

### 测试交易所连接

```
POST /api/v1/credentials/test
```

**请求体**：`CredentialTestRequest`

**说明**：底层调用 `test_exchange_connection()`，支持：
- 出口 IP 检测（`ifconfig.me/ip`）
- Binance `-2015` 跨市场自动探测 + 双语提示
- Demo 模式检测（12+ key 变体）
- 并发限制（`threading.Semaphore(5)`）

### 获取出口公网 IP

```
GET /api/v1/credentials/egress-ip
```

**响应**：
```json
{
  "ipv4": "203.0.113.1",
  "ipv6": null,
  "ip": "203.0.113.1"
}
```

**说明**：用于交易所 API Key 的 IP 白名单配置。优先返回 IPv4，否则 IPv6。

### 桌面券商策略探测

```
GET /api/v1/credentials/desktop-brokers-policy
```

**响应**：
```json
{
  "allow_local_desktop_brokers": false,
  "disabled_message": "当前部署环境已关闭 IBKR / MT5..."
}
```

**说明**：前端在保存或测试 IBKR/MT5 凭证前调用，判断当前部署环境是否允许配置本地桌面券商（TWS/MT5 终端）。SaaS/云容器部署默认返回 `false`。

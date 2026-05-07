# UF Stock Assistant — AI 分析记忆与反射校准系统

> 本文档描述 AI 分析记忆、历史验证、相似模式匹配和阈值校准的业务规则、数据模型与 API 接口。

---

## 1. 系统概述

分析记忆与反射校准系统为 UF Stock Assistant 提供 AI 决策的自我改进能力：

- **分析记忆**：持久化每次 AI 分析结果（决策、置信度、共识分、技术指标快照）
- **历史验证**：定期比对分析时的价格与当前价格，计算实际收益率，判断决策正确性
- **相似模式匹配**：基于 RSI / MACD / MA / 波动率检索历史同类技术指标模式
- **用户反馈**：收集用户对分析质量的显式反馈
- **离线校准**：Grid Search 最优 BUY/SELL/HOLD 阈值，持续提升决策准确率

**默认状态**：反射 Worker 默认开启，校准默认开启。可通过环境变量关闭。

---

## 2. 业务规则

### 2.1 决策正确性判定

| 决策 | 正确条件 | 说明 |
|------|---------|------|
| BUY | actual_return_pct > +2% | 买入后上涨超过 2% |
| SELL | actual_return_pct < -2% | 卖出后下跌超过 2% |
| HOLD | \|actual_return_pct\| ≤ 5% | 持有期间波动不超过 5% |

**验证时机**：分析记录创建后至少 `REFLECTION_MIN_AGE_DAYS` 天（默认 7 天）才参与验证，避免短期噪音干扰。

### 2.2 阈值校准规则

**候选阈值**：绝对值网格 `[10, 12, 14, 16, 18, 20, 22, 25, 30]`

**评分逻辑**：
- score ≥ thr → BUY
- score ≤ -thr → SELL
- 否则 → HOLD

**最优选择**：
1. 优先最高准确率
2. 准确率相同时，优先更高 BUY+SELL 覆盖率（减少 HOLD 模糊区）

**默认阈值**（无历史记录时回退）：
- BUY ≥ 20.0
- SELL ≤ -20.0
- min_consensus_abs_override = 15.0
- quality_hold_threshold = 0.7

### 2.3 相似模式匹配权重

| 指标 | 权重 | 匹配方式 |
|------|------|---------|
| RSI | 0.30 | diff / 30 |
| MACD 方向 | 0.30 | 精确匹配（正/负/零） |
| MA 方向 | 0.25 | 精确匹配（above/below） |
| 波动率级别 | 0.15 | 同区间匹配（低波动 vs 高波动） |
| 历史正确 bonus | +0.10 | 该历史记录 was_correct = true |

### 2.4 校准触发条件

- 校准样本数 ≥ `AI_CALIBRATION_MIN_SAMPLES`（默认 80）
- 校准回溯天数 ≤ `AI_CALIBRATION_LOOKBACK_DAYS`（默认 30）
- 校准市场白名单：`AI_CALIBRATION_MARKETS`（默认 "Crypto"）

---

## 3. 数据模型

### 3.1 analysis_memory

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| user_id | String(64) | 用户标识（可选） |
| market | String(50) | 市场类型（AStock / Crypto / USStock） |
| symbol | String(50) | 标的代码 |
| decision | String(10) | BUY / SELL / HOLD |
| confidence | Integer | 置信度 0-100 |
| price_at_analysis | Numeric(24,8) | 分析时价格 |
| summary | Text | 分析摘要 |
| reasons | JSON | 决策理由列表 |
| scores | JSON | 各维度评分 |
| indicators_snapshot | JSON | 技术指标快照 |
| raw_result | JSON | 原始分析结果 |
| consensus_score | Numeric(24,8) | 共识分 |
| consensus_abs | Numeric(24,8) | 共识绝对值 |
| agreement_ratio | Numeric(10,6) | 模型一致率 |
| quality_multiplier | Numeric(10,6) | 质量系数 |
| task_status | String(20) | completed / failed |
| task_error | Text | 错误信息 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |
| validated_at | DateTime | 验证时间 |
| actual_return_pct | Numeric(10,4) | 实际收益率 |
| was_correct | Boolean | 决策是否正确 |
| user_feedback | String(20) | 用户反馈 |
| feedback_at | DateTime | 反馈时间 |

### 3.2 ai_calibration

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| market | String(50) | 市场类型 |
| buy_threshold | Numeric(10,4) | BUY 阈值 |
| sell_threshold | Numeric(10,4) | SELL 阈值 |
| min_consensus_abs_override | Numeric(10,4) | 最小共识绝对值覆盖 |
| quality_hold_threshold | Numeric(10,4) | HOLD 质量阈值 |
| best_accuracy | Numeric(10,4) | 最佳准确率 |
| sample_count | Integer | 样本数 |
| validated_count | Integer | 验证记录数 |
| created_at | DateTime | 创建时间 |
| validated_at | DateTime | 校准时间 |

---

## 4. API 接口

### 4.1 获取用户分析历史

```
GET /api/v1/analysis/history?page=1&page_size=20
Header: user_id (default: "default")
```

**响应**：
```json
{
  "code": "success",
  "data": {
    "items": [...],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "pages": 3
  }
}
```

### 4.2 获取标的近期分析

```
GET /api/v1/analysis/history/{market}/{symbol}?days=7&limit=5
```

**响应**：
```json
{
  "code": "success",
  "data": {
    "items": [...],
    "market": "AStock",
    "symbol": "000001.SZ"
  }
}
```

### 4.3 获取相似技术指标模式

```
GET /api/v1/analysis/similar/{market}/{symbol}?indicators={}&limit=3
```

**Query**：
- `indicators`：JSON 字符串，当前技术指标（如 `{"rsi_14": 30, "macd_signal": 1.5}`）

**响应**：
```json
{
  "code": "success",
  "data": {
    "patterns": [
      {"memory_id": 1, "similarity": 0.92, "decision": "BUY", "was_correct": true}
    ]
  }
}
```

### 4.4 记录用户反馈

```
POST /api/v1/analysis/feedback
Content-Type: application/json
```

**请求体**：
```json
{
  "memory_id": 123,
  "feedback": "helpful"
}
```

**feedback 枚举**：`helpful`, `not_helpful`, `accurate`, `inaccurate`

**响应**：
```json
{
  "code": "success",
  "data": {"recorded": true}
}
```

### 4.5 获取性能统计

```
GET /api/v1/analysis/stats?market=AStock&symbol=000001.SZ&days=30
```

**响应**：
```json
{
  "code": "success",
  "data": {
    "total": 50,
    "validated": 30,
    "correct": 18,
    "accuracy_pct": 60.0,
    "decision_distribution": {"BUY": 20, "SELL": 10, "HOLD": 20}
  }
}
```

### 4.6 获取校准配置

```
GET /api/v1/analysis/calibration/{market}
```

**响应**：
```json
{
  "code": "success",
  "data": {
    "market": "Crypto",
    "config": {
      "buy_threshold": 20.0,
      "sell_threshold": -20.0,
      "min_consensus_abs_override": 15.0,
      "quality_hold_threshold": 0.7
    }
  }
}
```

---

## 5. 配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `STOCK_ASSISTANT_REFLECTION_ENABLED` | `true` | 是否启用反射 Worker |
| `STOCK_ASSISTANT_REFLECTION_INTERVAL_SECONDS` | `86400` | Worker 执行间隔（秒） |
| `STOCK_ASSISTANT_REFLECTION_MIN_AGE_DAYS` | `7` | 验证最小历史天数 |
| `STOCK_ASSISTANT_REFLECTION_VALIDATE_LIMIT` | `200` | 单次验证最大条数 |
| `STOCK_ASSISTANT_REFLECTION_CALIBRATION_ENABLED` | `true` | 是否启用离线校准 |
| `STOCK_ASSISTANT_REFLECTION_CALIBRATION_MARKETS` | `Crypto` | 校准市场，逗号分隔 |
| `STOCK_ASSISTANT_REFLECTION_CALIBRATION_LOOKBACK_DAYS` | `30` | 校准回溯天数 |
| `STOCK_ASSISTANT_REFLECTION_CALIBRATION_MIN_SAMPLES` | `80` | 校准最小样本数 |

---

## 6. 运营注意事项

1. **首次部署**：无历史记录时校准返回默认值，随着分析次数积累自动优化
2. **验证延迟**：新分析记录需等待 `MIN_AGE_DAYS` 后才参与验证和校准
3. **市场隔离**：AStock / Crypto / USStock 的阈值独立校准，互不影响
4. **Worker 安全**：反射 Worker 在独立 daemon 线程运行，异常被捕获不影响主服务
5. **价格来源**：AStock 验证使用 `get_stock_realtime()`（东财 API），Crypto 需后续扩展

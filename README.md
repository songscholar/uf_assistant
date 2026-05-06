# UF Stock Assistant — 智能股票助手

基于 LangChain + LangGraph 框架构建的企业级智能股票助手 Agent，支持股票数据分析、交易策略执行、虚拟货币行情、市场分析、自动选股、模拟交易、文件解析等功能。

---

## 功能特性

### 核心能力
- **股票数据**：A 股实时行情、历史 K 线、财务数据、资金流向
- **虚拟货币**：支持主流币种行情查询（BTC/ETH 等，通过 CCXT）
- **交易策略**：内置均线交叉、MACD、RSI、布林带策略，支持自定义策略
- **智能选股**：基于策略条件批量筛选股票
- **市场分析**：大盘走向、板块热点、龙虎榜、每日市场报告
- **模拟交易**：下单、持仓管理、订单查询、投资组合分析
- **对话历史**：上下文管理，自动压缩机制（超过 20 轮自动摘要）
- **文件解析**：支持 PDF、DOCX、XLSX、TXT、图片 OCR
- **多 LLM 支持**：Kimi、OpenAI、DeepSeek、Xiaomi 等提供商切换

### 技术架构
- **AI 框架**：LangChain + LangGraph（状态机 Agent）
- **API 服务**：FastAPI + Uvicorn
- **数据存储**：SQLite（开发）/ PostgreSQL（生产）
- **股票数据**：AKShare（A股）
- **虚拟货币**：CCXT（Binance 等）
- **日志系统**：structlog + JSON 结构化 + 文件轮转

---

## 快速开始

### 环境要求

- Python >= 3.11
- pip 或 uv

### 安装

```bash
# 克隆仓库
git clone <repository-url>
cd uf-stock-assistant

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -e ".[dev]"
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，配置 LLM API Key
vim .env
```

最小配置示例：
```env
STOCK_ASSISTANT_LLM_PROVIDER=kimi
KIMI_LLM_API_KEY=your-api-key-here
KIMI_LLM_BASE_URL=https://api.moonshot.cn/v1/chat/completions
```

### 启动 API 服务

```bash
# 开发模式（热重载）
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

服务启动后访问：
- API 文档：`http://127.0.0.1:8000/docs`（Swagger UI）
- 健康检查：`http://127.0.0.1:8000/health`

---

## API 接口文档

### 接口前缀
所有接口前缀为 `/api/v1`

### 1. 对话接口

#### 发送消息
```http
POST /api/v1/chat
Content-Type: application/json

{
  "message": "分析贵州茅台",
  "conversation_id": "可选，留空创建新会话",
  "user_id": "default"
}
```

响应：
```json
{
  "conversation_id": "uuid",
  "answer": "分析结果...",
  "tools_used": []
}
```

#### 获取会话列表
```http
GET /api/v1/conversations?user_id=default&limit=20
```

#### 获取会话详情
```http
GET /api/v1/conversations/{conversation_id}
```

#### 删除会话
```http
DELETE /api/v1/conversations/{conversation_id}
```

#### 创建会话
```http
POST /api/v1/conversations?user_id=default&title=标题
```

---

### 2. 股票数据接口

#### 搜索股票
```http
GET /api/v1/stock/search?keyword=平安&limit=10
```

#### 股票基本信息
```http
GET /api/v1/stock/000001/info
```

#### 实时行情
```http
GET /api/v1/stock/000001/realtime
```

#### 历史 K 线
```http
GET /api/v1/stock/000001/history?period=daily&start=2024-01-01&end=2024-12-31&limit=100
```

参数：
- `period`: daily / weekly / monthly
- `start`: 开始日期 YYYY-MM-DD
- `end`: 结束日期 YYYY-MM-DD
- `limit`: 返回条数，默认 100

#### 财务数据
```http
GET /api/v1/stock/000001/financial
```

#### 资金流向
```http
GET /api/v1/stock/000001/capital-flow
```

---

### 3. 市场数据接口

#### 市场概况
```http
GET /api/v1/market/overview
```

#### 大盘指数
```http
GET /api/v1/market/indices
```

#### 板块热点
```http
GET /api/v1/market/sectors
```

#### 龙虎榜
```http
GET /api/v1/market/longhu?date=2024-01-01
```

#### 北向资金
```http
GET /api/v1/market/northbound
```

---

### 4. 虚拟货币接口

#### 获取价格
```http
GET /api/v1/crypto/price?symbol=BTC&exchange=binance
```

#### 行情摘要
```http
GET /api/v1/crypto/ticker?symbol=BTC/USDT
```

#### 市值排行
```http
GET /api/v1/crypto/top?limit=20
```

#### K 线数据
```http
GET /api/v1/crypto/ohlcv?symbol=BTC/USDT&timeframe=1d&limit=100
```

---

### 5. 交易接口（模拟）

#### 下单
```http
POST /api/v1/trading/order
Content-Type: application/json

{
  "symbol": "000001",
  "side": "buy",
  "quantity": 100,
  "price": 10.5,
  "order_type": "limit"
}
```

#### 获取持仓
```http
GET /api/v1/trading/positions
```

#### 获取指定持仓
```http
GET /api/v1/trading/position/000001
```

#### 获取订单列表
```http
GET /api/v1/trading/orders?status=filled
```

#### 取消订单
```http
DELETE /api/v1/trading/orders/{order_id}
```

#### 投资组合
```http
GET /api/v1/trading/portfolio
```

---

### 6. 策略接口

#### 列出策略
```http
GET /api/v1/strategies
```

#### 执行策略分析
```http
POST /api/v1/strategies/ma_crossover/evaluate
Content-Type: application/json

{
  "symbol": "000001",
  "params": {"short_window": 5, "long_window": 20}
}
```

#### 选股
```http
POST /api/v1/strategies/pick
Content-Type: application/json

{
  "strategy_key": "rsi",
  "symbols": ["000001", "000002", "600000"],
  "params": {"period": 14},
  "min_confidence": 0.3
}
```

#### 快速筛选
```http
POST /api/v1/strategies/screen
Content-Type: application/json

{
  "min_price": 5,
  "max_price": 50,
  "min_change_pct": -5,
  "limit": 20
}
```

#### 创建自定义策略
```http
POST /api/v1/strategies/custom
Content-Type: application/json

{
  "description": "创建一个策略：当5日均线上穿10日均线且成交量放大1.5倍时买入"
}
```

#### 每日市场报告
```http
GET /api/v1/market/daily-report
```

---

### 7. 文件上传接口

#### 上传文件
```http
POST /api/v1/upload
Content-Type: multipart/form-data

file: <文件>
```

支持格式：PDF、DOCX、XLSX、TXT、PNG、JPG、JPEG

#### 批量上传
```http
POST /api/v1/upload/batch
Content-Type: multipart/form-data

files: <文件1>
files: <文件2>
```

---

## 项目结构

```
.
├── app/                        # 主应用目录
│   ├── core/                   # 核心框架层
│   │   ├── config.py           # Pydantic Settings 配置管理
│   │   ├── constants.py        # 项目常量、枚举定义
│   │   ├── exceptions.py       # 业务异常体系
│   │   ├── llm_adapter.py      # LLM 统一调用层（多提供商切换）
│   │   └── logging.py          # 企业级日志系统
│   ├── agents/                 # 智能体定义
│   │   ├── prompts.py          # 系统提示词模板
│   │   └── stock_assistant.py  # 股票助手 Agent（LangGraph）
│   ├── tools/                  # 工具层
│   │   ├── stock_data.py       # 股票数据（AKShare）
│   │   ├── crypto_data.py      # 虚拟货币（CCXT）
│   │   ├── market.py           # 市场数据
│   │   ├── file_parser.py      # 文件/图片解析
│   │   └── trading.py          # 模拟交易
│   ├── strategies/             # 交易策略模块
│   │   ├── base.py             # 策略基类
│   │   ├── builtin/            # 内置策略
│   │   │   ├── ma_crossover.py # 均线交叉
│   │   │   ├── macd.py         # MACD
│   │   │   ├── rsi.py          # RSI 超卖
│   │   │   └── bollinger.py    # 布林带
│   │   ├── registry.py         # 策略注册表
│   │   └── custom.py           # 自定义策略接口
│   ├── memory/                 # 对话与记忆
│   │   ├── conversation.py     # 对话存储（SQLAlchemy）
│   │   ├── compressor.py       # 上下文压缩
│   │   └── manager.py          # 记忆管理器
│   ├── services/               # 业务服务层
│   │   ├── stock_picker.py     # 选股服务
│   │   └── market_analyzer.py  # 市场分析服务
│   ├── api/                    # API 服务层
│   │   ├── main.py             # FastAPI 主应用
│   │   └── routers/            # 路由模块
│   │       ├── chat.py         # 对话
│   │       ├── stock.py        # 股票数据
│   │       ├── market.py       # 市场数据
│   │       ├── crypto.py       # 虚拟货币
│   │       ├── trading.py      # 交易
│   │       ├── strategy.py     # 策略
│   │       └── upload.py       # 文件上传
│   └── data/                   # 数据层
├── tests/                      # 测试目录
├── docs/                       # 项目文档
│   └── system/                 # 系统文档
├── logs/                       # 运行日志
├── data/                       # 本地数据（SQLite）
├── pyproject.toml              # 项目配置
├── .env.example                # 环境变量模板
├── AGENTS.md                   # 开发规范
├── DEVELOPMENT_LOG.md          # 开发日志
└── README.md                   # 本文件
```

---

## 开发规范

详见 [AGENTS.md](AGENTS.md)，包含：
- 代码风格与分层约束
- 开发工作流规范
- 日志与文档要求
- 安全注意事项

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

## LLM 配置

支持多提供商切换，通过环境变量配置：

```bash
# 选择提供商
STOCK_ASSISTANT_LLM_PROVIDER=kimi

# Kimi 配置
KIMI_LLM_API_KEY=your-key
KIMI_LLM_MODEL=kimi-k2

# OpenAI 配置
OPENAI_LLM_API_KEY=your-key
OPENAI_LLM_MODEL=gpt-4o

# DeepSeek 配置
DEEPSEEK_LLM_API_KEY=your-key
```

---

## License

[LICENSE](LICENSE)

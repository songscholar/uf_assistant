# UF Stock Assistant — 智能股票助手

基于 LangChain 框架构建的企业级股票助手 Agent，支持股票数据分析、交易策略执行、虚拟货币行情、市场分析等功能。

## 功能特性

- **股票数据**：获取 A 股实时行情、历史数据、财务数据
- **虚拟货币**：支持主流虚拟货币行情查询（通过 CCXT）
- **交易策略**：内置多种经典交易策略，支持自定义策略
- **智能选股**：基于策略条件筛选股票
- **市场分析**：大盘走向分析、板块热点追踪
- **龙虎榜**：每日龙虎榜数据展示
- **持仓管理**：用户持仓展示与分析
- **模拟交易**：支持模拟下单（支持真实交易对接扩展）
- **对话历史**：上下文管理，自动压缩机制
- **文件解析**：支持上传文件、图片解析
- **多 LLM 支持**：支持 Kimi、OpenAI、DeepSeek、Xiaomi 等提供商切换

## 快速开始

### 环境要求

- Python >= 3.11
- pip 或 uv

### 安装

```bash
# 克隆仓库
git clone <repository-url>
cd uf_assistant

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -e ".[dev]"
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，配置 LLM API Key
vim .env
```

### 运行

```bash
# 启动 API 服务
uvicorn app.api.main:app --reload

# 运行 CLI
python -m app.cli
```

## 项目结构

```
app/
├── core/           # 核心框架（配置、日志、LLM 适配器）
├── agents/         # 智能体定义
├── tools/          # 工具层（股票/虚拟货币/文件解析）
├── strategies/     # 交易策略模块
├── memory/         # 对话历史与上下文压缩
├── data/           # 数据层
├── api/            # API 服务层
└── services/       # 业务服务层
```

## LLM 配置

支持多提供商切换，通过环境变量配置：

```bash
# 选择提供商
STOCK_ASSISTANT_LLM_PROVIDER=kimi

# Kimi 配置
KIMI_LLM_API_KEY=your-api-key
KIMI_LLM_MODEL=kimi-k2
KIMI_LLM_BASE_URL=https://api.moonshot.cn/v1/chat/completions

# OpenAI 配置（可选）
OPENAI_LLM_API_KEY=your-api-key
OPENAI_LLM_MODEL=gpt-4o
```

## 开发

```bash
# 运行测试
pytest -q

# 代码检查
ruff check .
mypy app/
```

## 文档

- [开发规范](AGENTS.md)
- [开发日志](DEVELOPMENT_LOG.md)
- [系统文档](docs/system/)
- [业务文档](docs/business/)

## License

[LICENSE](LICENSE)

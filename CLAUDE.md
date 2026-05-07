# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UF Stock Assistant — an intelligent stock assistant Agent built on LangChain + LangGraph. Supports A-share stock data analysis, trading strategies, crypto quotes, market analysis, stock screening, simulated trading, file parsing, and multi-turn conversation with context compression.

- Python 3.11+, FastAPI backend, React 19 + Vite 8 frontend
- LangGraph state-machine agent with multi-provider LLM support (Kimi, OpenAI, DeepSeek, Xiaomi)

## Commands

### Backend

```bash
pip install -e ".[dev]"                          # Install dependencies
uvicorn app.api.main:app --reload --port 8000    # Dev server (hot reload)
pytest -q                                         # Run all tests
pytest -q tests/test_chat.py                      # Run single test file
pytest --cov=app --cov-report=term-missing        # Tests with coverage
ruff check .                                      # Lint
mypy app/                                         # Type check
python3 -m py_compile app/**/*.py                 # Syntax check
```

### Frontend

```bash
cd frontend
npm install               # Install dependencies
npm run dev               # Dev server on :5173 (proxies /api → :8000)
npm run build             # Production build (tsc + vite)
npm run preview           # Preview production build
```

### Setup

```bash
cp .env.example .env      # Then fill in LLM API keys
```

## Architecture

### Request Flow

```
React UI → axios POST /api/v1/chat → FastAPI router
  → StockAssistantAgent.chat() → MemoryManager (load context)
  → LangGraph StateGraph: agent → [tool_calls?] → tools → agent → finalize
  → LLM (via llm_adapter) → tool execution → formatted response
  → Save to memory → JSON response
```

### Backend Layers (`app/`)

| Layer | Directory | Responsibility |
|-------|-----------|---------------|
| Core | `app/core/` | Config (Pydantic Settings), LLM adapter (multi-provider), exceptions, logging (structlog), constants (StrEnum) |
| Auth | `app/auth/` | JWT auth (HS256), bcrypt password hashing, OAuth (Google/GitHub), email verification, RBAC (viewer/user/manager/admin), rate limiting, Turnstile, security audit, user CRUD, credits/VIP |
| Agent | `app/agents/` | LangGraph state-machine (`StockAssistantAgent`), system prompts |
| Tools | `app/tools/` | LangChain tools: stock_data (AKShare), crypto_data (CCXT), market, trading, file_parser, strategy_tools |
| Strategies | `app/strategies/` | Dual-paradigm strategy engine: evaluate mode (4 builtin: MA/MACD/RSI/Bollinger), IndicatorStrategy (df['buy']/df['sell']), ScriptStrategy (on_bar event-driven). 8-way signals (open/close/add/reduce × long/short), signal dedup (memory + DB), PriceCache, bot mode (per-tick on_bar), script runtime state persistence, fee rate caching. Trading executor → pending_orders queue → PendingOrderWorker (stale reclaim, maker-then-market, position sync). Exchange client (CCXT + simulated stock), notifier (Telegram/Email/Webhook), strategy service (CRUD + batch ops) |
| Memory | `app/memory/` | `ConversationStore` (SQLAlchemy), `ContextCompressor` (auto-compresses at 20 msgs, keeps recent 10), `MemoryManager` |
| Services | `app/services/` | Higher-level business logic: `stock_picker`, `market_analyzer` |
| API | `app/api/` | FastAPI app + routers: chat, stock, market, crypto, trading, strategy, upload, auth, user, billing |

### Frontend (`frontend/src/`)

| Layer | Location | Notes |
|-------|----------|-------|
| Routing | `App.tsx` | react-router-dom v7. Routes: `/login`, `/register`, `/chat`, `/market`, `/stock/:symbol`, `/strategy`, `/trading`, `/crypto`. ProtectedRoute guards all non-auth routes. Default `/` → `/chat` |
| State | `stores/` | Zustand stores: `chatStore`, `themeStore` (dark/light/rain), `rainStore`, `authStore` (JWT token, user info, login/register/logout) |
| API Client | `lib/api.ts` | Axios instance, base URL `/api` |
| Path Alias | `@/` | Maps to `frontend/src/` (configured in vite.config.ts + tsconfig) |

### LLM Multi-Provider

`app/core/llm_adapter.py` — `LlmService.from_env()` selects provider based on `STOCK_ASSISTANT_LLM_PROVIDER`. `LangChainLlmAdapter` wraps the custom HTTP client for LangChain compatibility. All providers use OpenAI-compatible HTTP format.

### Error Handling

All business exceptions inherit `AssistantException` with `code`, `message`, `details`. Specific types: `ConfigError`, `LlmError`, `DataProviderError`, `TradingError`, `StrategyError`, `ValidationError`, `FileParseError`, `MemoryError`. FastAPI global handlers return structured JSON.

## Code Conventions

- All Python code must have type annotations. Use `from __future__ import annotations` and `X | None` syntax.
- Enums use `StrEnum` (Python 3.11+).
- JSON output: `ensure_ascii=False`.
- New logic goes in the correct layer — no cross-layer direct calls.
- Business exceptions must inherit `AssistantException` (never bare `Exception`).
- Linting: ruff (line-length=120, target py311, select E/F/I/W/UP/B/C4/SIM).
- Type checking: mypy strict mode.

## Git Conventions

- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Code changes must be logged in `DEVELOPMENT_LOG.md`
- Never commit `.env`, logs, database files, or temp outputs
- File outputs default to `examples/` directory

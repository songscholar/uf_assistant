export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  status?: 'sending' | 'streaming' | 'complete' | 'error';
  tools_used?: ToolInfo[];
}

export interface ToolInfo {
  name: string;
  params: Record<string, unknown>;
  result?: unknown;
}

export interface StockInfo {
  symbol: string;
  name: string;
  industry?: string;
  market?: string;
}

export interface StockRealtime {
  symbol: string;
  name: string;
  current_price: number;
  change: number;
  change_percent: number;
  open: number;
  high: number;
  low: number;
  prev_close: number;
  volume: number;
  amount: number;
}

export interface KlineData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketIndex {
  name: string;
  symbol: string;
  market?: string;
  value: number;
  change: number;
  change_percent: number;
}

export interface SectorData {
  name: string;
  change_percent: number;
}

export interface StrategyInfo {
  key: string;
  name: string;
  description: string;
}

export interface StrategySignal {
  direction: 'buy' | 'sell' | 'hold' | null;
  confidence: number | null;
  reason: string | null;
}

export interface Order {
  order_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number | null;
  order_type: string;
  status: string;
  created_at: string;
}

export interface Position {
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  pnl: number;
  pnl_percent: number;
}

export interface Portfolio {
  total_assets: number;
  available_cash: number;
  position_value: number;
  total_pnl: number;
  total_pnl_percent: number;
}

export interface CryptoPrice {
  symbol: string;
  price: number;
  change_24h: number;
  change_24h_percent: number;
  volume_24h: number;
  market_cap: number;
}

// ── 实盘交易类型 ─────────────────────────────────────────────────────────────

export interface TradingCredential {
  id: string;
  market: 'crypto' | 'a_share' | 'us_stock';
  name: string;
  api_key_masked: string;
  is_active: boolean;
  created_at: string;
}

export interface LiveOrder {
  id: string;
  market: string;
  symbol: string;
  side: 'buy' | 'sell';
  order_type: string;
  quantity: number;
  price?: number;
  status: string;
  filled_quantity: number;
  filled_price?: number;
  fee?: number;
  strategy_id?: string;
  mode: string;
  created_at: string;
}

export interface LivePosition {
  id: string;
  market: string;
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price?: number;
  unrealized_pnl?: number;
  realized_pnl: number;
  mode: string;
}

export interface PnLSummary {
  total_realized: number;
  total_unrealized: number;
  total_pnl: number;
  total_fee: number;
}

export interface TradeRecord {
  id: string;
  order_id: string;
  market: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  fee: number;
  timestamp: string;
}

// ── 策略引擎类型 ──────────────────────────────────────────────────────────

export interface StrategyListItem {
  id: string;
  name: string;
  type: string;
  status: string;
  created_at: string;
}

export interface BacktestRequest {
  code: string;
  symbol: string;
  params?: Record<string, unknown>;
}

export interface BacktestResult {
  total_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  total_trades: number;
  equity_curve: EquityPoint[];
  trades?: StrategyTrade[];
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface StrategyPositionItem {
  id: number;
  strategy_id: string;
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  highest_price?: number;
  lowest_price?: number;
  unrealized_pnl: number;
  updated_at: string;
}

export interface StrategyTrade {
  id: string;
  symbol: string;
  side: string;
  price: number;
  quantity: number;
  pnl: number;
  timestamp: string;
}

export interface StrategyLog {
  timestamp: string;
  level: string;
  message: string;
}

export interface Indicator {
  name: string;
  category: string;
  description: string;
}

export interface RuntimeMetrics {
  strategy_id: string;
  uptime: number;
  ticks_processed: number;
  signals_generated: number;
  last_tick_at: string;
}

export interface CodeQuality {
  score: number;
  issues: string[];
  suggestions: string[];
}

export interface ParseParamsResult {
  params: Array<{ name: string; type: string; default: unknown; description: string }>;
}

// ── 分析历史类型 ──────────────────────────────────────────────────────────

export interface AnalysisRecord {
  id: string;
  symbol: string;
  signal: string;
  confidence: number;
  summary: string;
  created_at: string;
}

export interface AnalysisStats {
  total_analyses: number;
  avg_confidence: number;
  signal_distribution: Record<string, number>;
}

// ── 会员/积分类型 ─────────────────────────────────────────────────────────

export interface BillingPlan {
  id: string;
  name: string;
  price: number;
  credits: number;
  features: string[];
  popular?: boolean;
}

export interface CreditBalance {
  balance: number;
  total_earned: number;
  total_spent: number;
}

export interface CreditLog {
  id: string;
  amount: number;
  type: string;
  description: string;
  created_at: string;
}

export interface MembershipInfo {
  level: string;
  expires_at: string;
  benefits: string[];
}

export interface UsdtPayment {
  address: string;
  amount: number;
  qr_code: string;
  status: string;
}

// ── 个人中心类型 ──────────────────────────────────────────────────────────

export interface UserProfile {
  username: string;
  email: string;
  avatar: string;
  created_at: string;
}

export interface NotificationSettings {
  email_enabled: boolean;
  telegram_enabled: boolean;
  browser_enabled: boolean;
}

export interface ChartTemplate {
  id: string;
  name: string;
  config: Record<string, unknown>;
  is_default: boolean;
}

// ── 管理后台类型 ──────────────────────────────────────────────────────────

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: string;
  credits: number;
  is_vip: boolean;
  created_at: string;
  last_login_at: string;
}

export interface AdminUserDetail extends AdminUser {
  login_count: number;
  credits_history: CreditLog[];
}

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

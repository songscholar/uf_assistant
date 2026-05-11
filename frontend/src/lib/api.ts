import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

const API_BASE = '/api/v1'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor: attach JWT token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Response interceptor: 401 → clean auth state (let router handle redirect)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  },
)

/**
 * 将常见英文网络/Axios 错误映射为中文用户友好提示。
 * 优先使用后端返回的 detail/message（已经是中文）。
 */
export function getErrorMessage(err: unknown, fallback = '操作失败，请稍后重试'): string {
  if (axios.isAxiosError(err)) {
    if (err.response?.data?.detail) return String(err.response.data.detail)
    if (err.response?.data?.message) return String(err.response.data.message)
    const msg = err.message || ''
    if (msg.includes('Network Error')) return '网络连接失败，请检查网络设置'
    if (msg.includes('timeout') || msg.includes('Timeout')) return '请求超时，请稍后重试'
    if (msg.includes('aborted') || msg.includes('canceled') || msg.includes('cancelled')) return '请求已取消'
    return fallback
  }
  if (err instanceof Error) {
    const msg = err.message || ''
    if (msg.includes('Network Error')) return '网络连接失败，请检查网络设置'
    if (msg.includes('timeout') || msg.includes('Timeout')) return '请求超时，请稍后重试'
    if (msg.includes('aborted') || msg.includes('canceled') || msg.includes('cancelled')) return '请求已取消'
    return msg || fallback
  }
  return fallback
}

// Chat APIs
export const chatApi = {
  sendMessage: (message: string, conversationId?: string, provider?: string) =>
    api.post('/chat', { message, conversation_id: conversationId, provider }),

  getProviders: () => api.get('/providers'),

  getConversations: () => api.get('/conversations'),

  getConversation: (id: string) => api.get(`/conversations/${id}`),

  createConversation: () => api.post('/conversations'),

  deleteConversation: (id: string) => api.delete(`/conversations/${id}`),
}

// Stock APIs
export const stockApi = {
  search: (q: string) => api.get('/stock/search', { params: { q } }),

  getInfo: (symbol: string) => api.get(`/stock/${symbol}/info`),

  getRealtime: (symbol: string) => api.get(`/stock/${symbol}/realtime`),

  getHistory: (symbol: string, period = 'daily') =>
    api.get(`/stock/${symbol}/history`, { params: { period } }),

  getFinancial: (symbol: string) => api.get(`/stock/${symbol}/financial`),

  getCapitalFlow: (symbol: string) => api.get(`/stock/${symbol}/capital-flow`),

  // Watchlist
  getWatchlist: () => api.get('/stock/watchlist'),
  addWatchlist: (symbol: string, name?: string) =>
    api.post('/stock/watchlist', { symbol, name }),
  deleteWatchlist: (symbol: string) => api.delete(`/stock/watchlist/${symbol}`),
}

// Market APIs
export const marketApi = {
  getOverview: () => api.get('/market/overview'),

  getIndices: () => api.get('/market/indices'),

  getSectors: () => api.get('/market/sectors'),

  getLonghu: () => api.get('/market/longhu'),

  getNorthbound: () => api.get('/market/northbound'),
}

// Strategy APIs
export const strategyApi = {
  list: () => api.get('/strategies'),

  evaluate: (key: string, symbol: string, params?: Record<string, unknown>) =>
    api.post(`/strategies/${key}/evaluate`, { symbol, params }),

  pick: (strategyKey: string, symbols: string[], params?: Record<string, unknown>) =>
    api.post('/strategies/pick', { strategy_key: strategyKey, symbols, params }),

  screen: (filters: Record<string, unknown>) =>
    api.post('/strategies/screen', filters),

  createCustom: (description: string) =>
    api.post('/strategies/custom', { description }),
}

// Trading APIs (模拟)
export const tradingApi = {
  submitOrder: (order: {
    symbol: string
    side: 'buy' | 'sell'
    quantity: number
    price?: number
    order_type?: string
  }) => api.post('/trading/order', order),

  getPositions: () => api.get('/trading/positions'),

  getOrders: () => api.get('/trading/orders'),

  cancelOrder: (id: string) => api.delete(`/trading/orders/${id}`),

  getPortfolio: () => api.get('/trading/portfolio'),
}

// Live Trading APIs (实盘)
export const liveTradingApi = {
  submitOrder: (order: {
    market: string
    symbol: string
    side: 'buy' | 'sell'
    order_type?: string
    quantity: number
    price?: number
    strategy_id?: string
  }) => api.post('/trading/live/order', order),

  getOrders: (params?: { market?: string; status?: string; limit?: number }) =>
    api.get('/trading/live/orders', { params }),

  cancelOrder: (id: string, market: string) =>
    api.post(`/trading/live/cancel/${id}`, null, { params: { market } }),

  getPositions: (market?: string) =>
    api.get('/trading/live/positions', { params: { market } }),

  syncPositions: (market: string) =>
    api.post('/trading/live/sync', null, { params: { market } }),

  getPnL: (market?: string) =>
    api.get('/trading/live/pnl', { params: { market } }),

  getBalance: (market: string) =>
    api.get('/trading/live/balance', { params: { market } }),

  getTrades: (params?: { market?: string; symbol?: string; limit?: number }) =>
    api.get('/trading/live/trades', { params }),
}

// Credentials APIs
export const credentialsApi = {
  list: () => api.get('/credentials'),

  add: (data: {
    market: string
    name: string
    api_key: string
    api_secret: string
    passphrase?: string
    extra_config?: Record<string, unknown>
  }) => api.post('/credentials', data),

  update: (id: string, data: Record<string, unknown>) =>
    api.put(`/credentials/${id}`, data),

  delete: (id: string) => api.delete(`/credentials/${id}`),

  test: (data: {
    market: string
    api_key: string
    api_secret: string
    passphrase?: string
    extra_config?: Record<string, unknown>
  }) => api.post('/credentials/test', data),
}

// Crypto APIs
export const cryptoApi = {
  getPrice: (symbol: string, exchange = 'gate') =>
    api.get('/crypto/price', { params: { symbol, exchange } }),

  getTicker: (symbol: string, exchange = 'gate') =>
    api.get('/crypto/ticker', { params: { symbol, exchange } }),

  getTop: (limit = 20, exchange = 'gate') =>
    api.get('/crypto/top', { params: { limit, exchange } }),

  getOhlcv: (symbol: string, timeframe = '1d', exchange = 'gate') =>
    api.get('/crypto/ohlcv', { params: { symbol, timeframe, exchange } }),
}

// Auth APIs
export const authApi = {
  login: (username: string, password: string) =>
    api.post('/auth/login', { username, password }),

  loginWithCode: (email: string, code: string) =>
    api.post('/auth/login-code', { email, code }),

  sendCode: (email: string, code_type: string) =>
    api.post('/auth/send-code', { email, code_type }),

  register: (data: { username: string; email: string; password: string; code: string; referral_code?: string }) =>
    api.post('/auth/register', data),

  resetPassword: (email: string, code: string, new_password: string) =>
    api.post('/auth/reset-password', { email, code, new_password }),

  changePassword: (old_password: string, new_password: string) =>
    api.post('/auth/change-password', { old_password, new_password }),

  getInfo: () => api.get('/auth/info'),

  getSecurityConfig: () => api.get('/auth/security-config'),
}

// Upload APIs
export const uploadApi = {
  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

// Strategy Engine APIs
export const strategyEngineApi = {
  listStrategies: () => api.get('/strategies/list'),
  backtest: (data: { code: string; symbol: string; params?: Record<string, unknown> }) =>
    api.post('/strategies/backtest', data),
  getIndicators: () => api.get('/strategies/indicators'),
  startStrategy: (id: string) => api.post(`/strategies/${id}/start`),
  stopStrategy: (id: string) => api.post(`/strategies/${id}/stop`),
  getPositions: () => api.get('/strategies/positions'),
  getTrades: (strategyId?: string) =>
    api.get('/strategies/trades', { params: strategyId ? { strategy_id: strategyId } : {} }),
  getEquityCurve: (strategyId: string) => api.get(`/strategies/${strategyId}/equity-curve`),
  getLogs: (strategyId: string) => api.get(`/strategies/${strategyId}/logs`),
  getCodeQuality: (strategyId: string) => api.get(`/strategies/${strategyId}/code-quality`),
  verifyCode: (code: string) => api.post('/strategies/verify-code', { code }),
  parseParams: (code: string) => api.post('/strategies/parse-params', { code }),
  executeIndicator: (name: string, symbol: string, params?: Record<string, unknown>) =>
    api.post(`/strategies/indicator/${name}/execute`, { symbol, params }),
  batchEvaluate: (symbols: string[], strategyKey: string) =>
    api.post('/strategies/batch', { symbols, strategy_key: strategyKey }),
  getExchangeSymbols: (exchange: string) => api.get(`/strategies/exchange-symbols/${exchange}`),
  getRuntimeMetrics: (strategyId: string) => api.get(`/strategies/${strategyId}/runtime-metrics`),
}

// Analysis History APIs
export const analysisApi = {
  getHistory: (params?: { page?: number; limit?: number; symbol?: string }) =>
    api.get('/analysis/history', { params }),
  getStats: () => api.get('/analysis/stats'),
  analyze: (symbol: string, marketType = 'stock') =>
    api.post('/analysis/analyze', { symbol, market_type: marketType }),
  feedback: (memoryId: number, feedback: string) =>
    api.post('/analysis/feedback', { memory_id: memoryId, feedback }),
  getLatest: (symbol: string) => api.get(`/analysis/latest/${symbol}`),
  getById: (id: string) => api.get(`/analysis/${id}`),
  delete: (id: string) => api.delete(`/analysis/${id}`),
  search: (query: string) => api.get('/analysis/search', { params: { q: query } }),
}

// Billing APIs
export const billingApi = {
  getPlans: () => api.get('/billing/plans'),
  getCredits: () => api.get('/billing/credits'),
  getCreditsLog: (params?: { page?: number; limit?: number }) =>
    api.get('/billing/credits/log', { params }),
  getMembership: () => api.get('/billing/membership'),
  subscribe: (plan: string, channel: string) => api.post('/billing/subscribe', { plan, channel }),
  createPayOrder: (data: { plan: string; channel: string; amount?: number }) =>
    api.post('/billing/pay/create', data),
  getPayOrder: (orderId: number) => api.get(`/billing/pay/${orderId}`),
  mockConfirm: (orderId: number) => api.post(`/billing/pay/${orderId}/mock-confirm`),
  createUsdtPayment: (plan: string) => api.post('/billing/usdt/create', { plan }),
  checkUsdtPayment: (paymentId: string) => api.get(`/billing/usdt/${paymentId}`),
}

// User Self-Service APIs
export const userApi = {
  getProfile: () => api.get('/user/profile'),
  updateProfile: (data: Record<string, unknown>) => api.put('/user/profile', data),
  changePassword: (old_password: string, new_password: string) =>
    api.post('/user/change-password', { old_password, new_password }),
  getNotificationSettings: () => api.get('/user/notification-settings'),
  updateNotificationSettings: (settings: Record<string, boolean>) =>
    api.put('/user/notification-settings', settings),
  getChartTemplates: () => api.get('/user/chart-templates'),
  createChartTemplate: (data: { name: string; config: Record<string, unknown>; is_default?: boolean }) =>
    api.post('/user/chart-templates', data),
  updateChartTemplate: (id: string, data: Record<string, unknown>) =>
    api.put(`/user/chart-templates/${id}`, data),
  deleteChartTemplate: (id: string) => api.delete(`/user/chart-templates/${id}`),
}

// User Admin APIs
export const userAdminApi = {
  listUsers: (params?: { page?: number; limit?: number; role?: string }) =>
    api.get('/admin/users', { params }),
  getUserDetail: (id: string) => api.get(`/admin/users/${id}`),
  createUser: (data: { username: string; email: string; password: string; role?: string }) =>
    api.post('/admin/users', data),
  updateUser: (id: string, data: Record<string, unknown>) => api.put(`/admin/users/${id}`, data),
  deleteUser: (id: string) => api.delete(`/admin/users/${id}`),
  getRoles: () => api.get('/admin/roles'),
  setCredits: (id: string, credits: number) => api.post(`/admin/users/${id}/credits`, { credits }),
  setVip: (id: string, is_vip: boolean) => api.post(`/admin/users/${id}/vip`, { is_vip }),
  getCreditsLog: (id: string) => api.get(`/admin/users/${id}/credits-log`),
  batchUpdate: (userIds: string[], data: Record<string, unknown>) =>
    api.post('/admin/users/batch', { user_ids: userIds, ...data }),
  getStats: () => api.get('/admin/stats'),
}

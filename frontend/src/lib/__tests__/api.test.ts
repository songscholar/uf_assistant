import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock axios before importing api
const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      put: mockPut,
      delete: mockDelete,
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    })),
  },
}))

// Now import the api modules
const {
  strategyEngineApi,
  analysisApi,
  billingApi,
  userApi,
  userAdminApi,
} = await import('../api')

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue({ data: {} })
  mockPost.mockResolvedValue({ data: {} })
  mockPut.mockResolvedValue({ data: {} })
  mockDelete.mockResolvedValue({ data: {} })
})

describe('strategyEngineApi', () => {
  it('listStrategies calls GET /strategies/list', async () => {
    await strategyEngineApi.listStrategies()
    expect(mockGet).toHaveBeenCalledWith('/strategies/list')
  })

  it('backtest calls POST /strategies/backtest', async () => {
    const data = { code: 'test', symbol: '600519' }
    await strategyEngineApi.backtest(data)
    expect(mockPost).toHaveBeenCalledWith('/strategies/backtest', data)
  })

  it('getIndicators calls GET /strategies/indicators', async () => {
    await strategyEngineApi.getIndicators()
    expect(mockGet).toHaveBeenCalledWith('/strategies/indicators')
  })

  it('startStrategy calls POST with correct path', async () => {
    await strategyEngineApi.startStrategy('abc')
    expect(mockPost).toHaveBeenCalledWith('/strategies/abc/start')
  })

  it('stopStrategy calls POST with correct path', async () => {
    await strategyEngineApi.stopStrategy('abc')
    expect(mockPost).toHaveBeenCalledWith('/strategies/abc/stop')
  })

  it('getPositions calls GET /strategies/positions', async () => {
    await strategyEngineApi.getPositions()
    expect(mockGet).toHaveBeenCalledWith('/strategies/positions')
  })

  it('getTrades calls GET /strategies/trades', async () => {
    await strategyEngineApi.getTrades()
    expect(mockGet).toHaveBeenCalledWith('/strategies/trades', { params: {} })
  })

  it('getTrades with strategyId passes param', async () => {
    await strategyEngineApi.getTrades('s1')
    expect(mockGet).toHaveBeenCalledWith('/strategies/trades', { params: { strategy_id: 's1' } })
  })

  it('getEquityCurve calls correct path', async () => {
    await strategyEngineApi.getEquityCurve('s1')
    expect(mockGet).toHaveBeenCalledWith('/strategies/s1/equity-curve')
  })

  it('executeIndicator calls POST with symbol and params', async () => {
    await strategyEngineApi.executeIndicator('rsi', '600519', { period: 14 })
    expect(mockPost).toHaveBeenCalledWith('/strategies/indicator/rsi/execute', { symbol: '600519', params: { period: 14 } })
  })
})

describe('analysisApi', () => {
  it('getHistory calls GET /analysis/history with params', async () => {
    await analysisApi.getHistory({ page: 2, limit: 10 })
    expect(mockGet).toHaveBeenCalledWith('/analysis/history', { params: { page: 2, limit: 10 } })
  })

  it('getStats calls GET /analysis/stats', async () => {
    await analysisApi.getStats()
    expect(mockGet).toHaveBeenCalledWith('/analysis/stats')
  })

  it('delete calls DELETE with id', async () => {
    await analysisApi.delete('123')
    expect(mockDelete).toHaveBeenCalledWith('/analysis/123')
  })
})

describe('billingApi', () => {
  it('getPlans calls GET /billing/plans', async () => {
    await billingApi.getPlans()
    expect(mockGet).toHaveBeenCalledWith('/billing/plans')
  })

  it('getCredits calls GET /billing/credits', async () => {
    await billingApi.getCredits()
    expect(mockGet).toHaveBeenCalledWith('/billing/credits')
  })

  it('subscribe calls POST with plan and channel', async () => {
    await billingApi.subscribe('pro', 'alipay')
    expect(mockPost).toHaveBeenCalledWith('/billing/subscribe', { plan: 'pro', channel: 'alipay' })
  })

  it('createUsdtPayment calls POST with plan', async () => {
    await billingApi.createUsdtPayment('pro')
    expect(mockPost).toHaveBeenCalledWith('/billing/usdt/create', { plan: 'pro' })
  })
})

describe('userApi', () => {
  it('getProfile calls GET /user/profile', async () => {
    await userApi.getProfile()
    expect(mockGet).toHaveBeenCalledWith('/user/profile')
  })

  it('updateProfile calls PUT with data', async () => {
    await userApi.updateProfile({ username: 'new' })
    expect(mockPut).toHaveBeenCalledWith('/user/profile', { username: 'new' })
  })

  it('getNotificationSettings calls correct path', async () => {
    await userApi.getNotificationSettings()
    expect(mockGet).toHaveBeenCalledWith('/user/notification-settings')
  })
})

describe('userAdminApi', () => {
  it('listUsers calls GET /admin/users with params', async () => {
    await userAdminApi.listUsers({ page: 1, limit: 20 })
    expect(mockGet).toHaveBeenCalledWith('/admin/users', { params: { page: 1, limit: 20 } })
  })

  it('createUser calls POST with user data', async () => {
    const data = { username: 'test', email: 'test@test.com', password: 'pass' }
    await userAdminApi.createUser(data)
    expect(mockPost).toHaveBeenCalledWith('/admin/users', data)
  })

  it('deleteUser calls DELETE', async () => {
    await userAdminApi.deleteUser('u1')
    expect(mockDelete).toHaveBeenCalledWith('/admin/users/u1')
  })

  it('setCredits calls POST with credits', async () => {
    await userAdminApi.setCredits('u1', 500)
    expect(mockPost).toHaveBeenCalledWith('/admin/users/u1/credits', { credits: 500 })
  })

  it('setVip calls POST with is_vip', async () => {
    await userAdminApi.setVip('u1', true)
    expect(mockPost).toHaveBeenCalledWith('/admin/users/u1/vip', { is_vip: true })
  })
})

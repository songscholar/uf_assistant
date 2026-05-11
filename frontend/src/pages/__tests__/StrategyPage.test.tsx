import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/render'
import StrategyPage from '../StrategyPage'

vi.mock('@/lib/api', () => ({
  strategyApi: {
    list: vi.fn().mockResolvedValue({
      data: {
        strategies: [
          { key: 'ma_crossover', name: '均线交叉', description: '基于短期与长期移动平均线的交叉信号' },
          { key: 'macd', name: 'MACD', description: '基于MACD指标的金叉死叉信号' },
        ],
      },
    }),
    evaluate: vi.fn().mockResolvedValue({
      data: { signal: { direction: 'buy', confidence: 0.8, reason: '金叉信号' } },
    }),
  },
  strategyEngineApi: {
    listStrategies: vi.fn().mockResolvedValue({ data: { strategies: [] } }),
    backtest: vi.fn().mockResolvedValue({ data: {} }),
    getIndicators: vi.fn().mockResolvedValue({ data: { indicators: [] } }),
    getPositions: vi.fn().mockResolvedValue({ data: [] }),
    getTrades: vi.fn().mockResolvedValue({ data: [] }),
    startStrategy: vi.fn(),
    stopStrategy: vi.fn(),
    getRuntimeMetrics: vi.fn(),
  },
}))

describe('StrategyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders tab navigation', () => {
    renderWithRouter(<StrategyPage />)
    const tabs = screen.getAllByText('策略库')
    expect(tabs.length).toBeGreaterThan(0)
    expect(screen.getByText('回测')).toBeInTheDocument()
    expect(screen.getByText('指标')).toBeInTheDocument()
    expect(screen.getByText('运行中')).toBeInTheDocument()
    expect(screen.getByText('持仓/交易')).toBeInTheDocument()
  })

  it('displays strategy cards by default', async () => {
    renderWithRouter(<StrategyPage />)
    await waitFor(() => {
      const ma = screen.getAllByText('均线交叉')
      expect(ma.length).toBeGreaterThan(0)
      const macd = screen.getAllByText('MACD')
      expect(macd.length).toBeGreaterThan(0)
    })
  })

  it('displays strategy descriptions', async () => {
    renderWithRouter(<StrategyPage />)
    await waitFor(() => {
      expect(screen.getAllByText('基于短期与长期移动平均线的交叉信号').length).toBeGreaterThan(0)
    })
  })

  it('renders screener section', async () => {
    renderWithRouter(<StrategyPage />)
    await waitFor(() => {
      expect(screen.getByText('选股器')).toBeInTheDocument()
    })
  })

  it('renders strategy detail and config buttons on cards', async () => {
    renderWithRouter(<StrategyPage />)
    await waitFor(() => {
      const detailButtons = screen.getAllByText('策略详情')
      expect(detailButtons.length).toBeGreaterThan(0)
      const configButtons = screen.getAllByText('调整配置')
      expect(configButtons.length).toBeGreaterThan(0)
    })
  })
})

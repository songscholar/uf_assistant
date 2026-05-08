import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/render'
import AnalysisPage from '../AnalysisPage'

// Mock API
vi.mock('@/lib/api', () => ({
  analysisApi: {
    getHistory: vi.fn().mockResolvedValue({
      data: {
        data: {
          items: [
            {
              id: 1,
              market: 'AStock',
              symbol: '600519',
              signal: 'BUY',
              confidence: 0.85,
              summary: '茅台技术面看涨',
              indicators: { rsi: 65, macd: 0.5 },
              created_at: '2026-05-08T10:00:00Z',
            },
            {
              id: 2,
              market: 'AStock',
              symbol: '000001',
              signal: 'SELL',
              confidence: 0.72,
              summary: '平安银行看跌',
              indicators: {},
              created_at: '2026-05-07T10:00:00Z',
            },
          ],
          total: 2,
        },
      },
    }),
    getStats: vi.fn().mockResolvedValue({
      data: {
        data: {
          total_analyses: 100,
          avg_confidence: 0.78,
          signal_distribution: { BUY: 45, SELL: 30, HOLD: 25 },
        },
      },
    }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    search: vi.fn().mockResolvedValue({ data: { data: { items: [] } } }),
  },
}))

describe('AnalysisPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page title', async () => {
    renderWithRouter(<AnalysisPage />)
    expect(screen.getByText('总分析次数')).toBeInTheDocument()
  })

  it('displays stats cards', async () => {
    renderWithRouter(<AnalysisPage />)
    await waitFor(() => {
      expect(screen.getByText('100')).toBeInTheDocument()
    })
  })

  it('displays analysis records in table', async () => {
    renderWithRouter(<AnalysisPage />)
    await waitFor(() => {
      expect(screen.getByText('600519')).toBeInTheDocument()
      expect(screen.getByText('000001')).toBeInTheDocument()
    })
  })

  it('displays signal badges', async () => {
    renderWithRouter(<AnalysisPage />)
    await waitFor(() => {
      expect(screen.getByText('BUY')).toBeInTheDocument()
      expect(screen.getByText('SELL')).toBeInTheDocument()
    })
  })

  it('renders search input', () => {
    renderWithRouter(<AnalysisPage />)
    expect(screen.getByPlaceholderText('搜索股票代码...')).toBeInTheDocument()
  })

  it('renders table headers', async () => {
    renderWithRouter(<AnalysisPage />)
    await waitFor(() => {
      expect(screen.getByText('代码')).toBeInTheDocument()
      expect(screen.getByText('信号')).toBeInTheDocument()
      expect(screen.getByText('置信度')).toBeInTheDocument()
    })
  })
})

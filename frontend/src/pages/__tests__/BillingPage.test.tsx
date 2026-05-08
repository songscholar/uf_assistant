import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/render'
import BillingPage from '../BillingPage'

vi.mock('@/lib/api', () => ({
  billingApi: {
    getPlans: vi.fn().mockResolvedValue({
      data: {
        data: {
          plans: [
            { id: 'free', name: '免费版', price: 0, credits: 100, features: ['基础功能'] },
            { id: 'pro', name: '专业版', price: 99, credits: 5000, features: ['全部功能'], popular: true },
          ],
        },
      },
    }),
    getMembership: vi.fn().mockResolvedValue({
      data: { data: { level: '专业版', expires_at: '2027-01-01', benefits: [] } },
    }),
    getCredits: vi.fn().mockResolvedValue({
      data: { data: { balance: 1500, total_earned: 5000, total_spent: 3500 } },
    }),
    getCreditsLog: vi.fn().mockResolvedValue({
      data: {
        data: {
          items: [
            { id: '1', amount: 100, type: 'earn', description: '签到奖励', created_at: '2026-05-08' },
            { id: '2', amount: -50, type: 'spend', description: 'AI 分析', created_at: '2026-05-07' },
          ],
          total: 2,
        },
      },
    }),
    subscribe: vi.fn().mockResolvedValue({ data: {} }),
    createUsdtPayment: vi.fn().mockResolvedValue({
      data: { data: { address: 'TAddr123', amount: 100, status: 'pending' } },
    }),
  },
}))

describe('BillingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders tab navigation', () => {
    renderWithRouter(<BillingPage />)
    expect(screen.getByText('会员套餐')).toBeInTheDocument()
    expect(screen.getByText('积分')).toBeInTheDocument()
    expect(screen.getByText('充值')).toBeInTheDocument()
  })

  it('displays plans by default', async () => {
    renderWithRouter(<BillingPage />)
    await waitFor(() => {
      expect(screen.getByText('免费版')).toBeInTheDocument()
      expect(screen.getByText('专业版')).toBeInTheDocument()
    })
  })

  it('displays current membership', async () => {
    renderWithRouter(<BillingPage />)
    await waitFor(() => {
      expect(screen.getByText(/当前会员/)).toBeInTheDocument()
    })
  })

  it('shows popular badge on recommended plan', async () => {
    renderWithRouter(<BillingPage />)
    await waitFor(() => {
      expect(screen.getByText('推荐')).toBeInTheDocument()
    })
  })

  it('displays plan features', async () => {
    renderWithRouter(<BillingPage />)
    await waitFor(() => {
      expect(screen.getByText('基础功能')).toBeInTheDocument()
      expect(screen.getByText('全部功能')).toBeInTheDocument()
    })
  })
})

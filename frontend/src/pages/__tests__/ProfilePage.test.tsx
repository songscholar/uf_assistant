import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/render'
import ProfilePage from '../ProfilePage'

// Mock auth store
vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn(() => ({
    user: { username: 'testuser', email: 'test@test.com', role: 'admin' },
  })),
}))

vi.mock('@/lib/api', () => ({
  userApi: {
    getProfile: vi.fn().mockResolvedValue({
      data: { data: { username: 'testuser', email: 'test@test.com', created_at: '2026-01-01' } },
    }),
    updateProfile: vi.fn().mockResolvedValue({ data: {} }),
    getNotificationSettings: vi.fn().mockResolvedValue({
      data: { data: { email_enabled: true, telegram_enabled: false, browser_enabled: true } },
    }),
    updateNotificationSettings: vi.fn().mockResolvedValue({ data: {} }),
    getChartTemplates: vi.fn().mockResolvedValue({
      data: { data: { templates: [{ id: '1', name: '默认模板', config: {}, is_default: true }] } },
    }),
    createChartTemplate: vi.fn().mockResolvedValue({ data: { data: { id: '2', name: '新模板', config: {}, is_default: false } } }),
    deleteChartTemplate: vi.fn().mockResolvedValue({ data: {} }),
    updateChartTemplate: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders profile section', async () => {
    renderWithRouter(<ProfilePage />)
    await waitFor(() => {
      expect(screen.getByText('个人信息')).toBeInTheDocument()
    })
  })

  it('displays username', async () => {
    renderWithRouter(<ProfilePage />)
    await waitFor(() => {
      expect(screen.getByText('testuser')).toBeInTheDocument()
    })
  })

  it('renders notification settings', async () => {
    renderWithRouter(<ProfilePage />)
    await waitFor(() => {
      expect(screen.getByText('通知设置')).toBeInTheDocument()
      expect(screen.getByText('邮件通知')).toBeInTheDocument()
      expect(screen.getByText('Telegram 通知')).toBeInTheDocument()
      expect(screen.getByText('浏览器通知')).toBeInTheDocument()
    })
  })

  it('renders chart templates section', async () => {
    renderWithRouter(<ProfilePage />)
    await waitFor(() => {
      expect(screen.getByText('图表模板')).toBeInTheDocument()
    })
  })

  it('shows admin user management link for admin users', async () => {
    renderWithRouter(<ProfilePage />)
    await waitFor(() => {
      expect(screen.getByText('用户管理')).toBeInTheDocument()
    })
  })

  it('displays chart template names', async () => {
    renderWithRouter(<ProfilePage />)
    await waitFor(() => {
      expect(screen.getByText('默认模板')).toBeInTheDocument()
    })
  })
})

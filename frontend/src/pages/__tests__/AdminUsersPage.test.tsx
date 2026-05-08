import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from '@/test/render'
import AdminUsersPage from '../AdminUsersPage'

vi.mock('@/lib/api', () => ({
  userAdminApi: {
    listUsers: vi.fn().mockResolvedValue({
      data: {
        data: {
          items: [
            { id: '1', username: 'admin1', email: 'admin@test.com', role: 'admin', credits: 1000, is_vip: true, created_at: '2026-01-01', last_login_at: '2026-05-08' },
            { id: '2', username: 'user1', email: 'user@test.com', role: 'user', credits: 500, is_vip: false, created_at: '2026-02-01', last_login_at: '2026-05-07' },
          ],
          total: 2,
        },
      },
    }),
    getStats: vi.fn().mockResolvedValue({
      data: { data: { total: 100, vip: 15, active_today: 30 } },
    }),
    deleteUser: vi.fn().mockResolvedValue({ data: {} }),
    setVip: vi.fn().mockResolvedValue({ data: {} }),
    setCredits: vi.fn().mockResolvedValue({ data: {} }),
    createUser: vi.fn().mockResolvedValue({ data: {} }),
    updateUser: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

describe('AdminUsersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders stats cards', async () => {
    renderWithRouter(<AdminUsersPage />)
    await waitFor(() => {
      expect(screen.getByText('总用户数')).toBeInTheDocument()
      expect(screen.getByText('VIP 用户')).toBeInTheDocument()
      expect(screen.getByText('今日活跃')).toBeInTheDocument()
    })
  })

  it('displays stats values', async () => {
    renderWithRouter(<AdminUsersPage />)
    await waitFor(() => {
      expect(screen.getByText('100')).toBeInTheDocument()
      expect(screen.getByText('15')).toBeInTheDocument()
      expect(screen.getByText('30')).toBeInTheDocument()
    })
  })

  it('renders user table', async () => {
    renderWithRouter(<AdminUsersPage />)
    await waitFor(() => {
      expect(screen.getByText('admin1')).toBeInTheDocument()
      expect(screen.getByText('user1')).toBeInTheDocument()
      expect(screen.getByText('admin@test.com')).toBeInTheDocument()
    })
  })

  it('displays role badges', async () => {
    renderWithRouter(<AdminUsersPage />)
    await waitFor(() => {
      const adminBadges = screen.getAllByText('admin')
      expect(adminBadges.length).toBeGreaterThan(0)
      expect(screen.getByText('user')).toBeInTheDocument()
    })
  })

  it('displays credits', async () => {
    renderWithRouter(<AdminUsersPage />)
    await waitFor(() => {
      expect(screen.getByText('1000')).toBeInTheDocument()
      expect(screen.getByText('500')).toBeInTheDocument()
    })
  })

  it('renders search input', () => {
    renderWithRouter(<AdminUsersPage />)
    expect(screen.getByPlaceholderText('搜索用户名或邮箱...')).toBeInTheDocument()
  })

  it('renders new user button', () => {
    renderWithRouter(<AdminUsersPage />)
    expect(screen.getByText('新建用户')).toBeInTheDocument()
  })

  it('renders role filter buttons', () => {
    renderWithRouter(<AdminUsersPage />)
    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getByText('管理员')).toBeInTheDocument()
    expect(screen.getByText('观察者')).toBeInTheDocument()
  })

  it('renders table headers', async () => {
    renderWithRouter(<AdminUsersPage />)
    await waitFor(() => {
      expect(screen.getByText('用户名')).toBeInTheDocument()
      expect(screen.getByText('邮箱')).toBeInTheDocument()
      expect(screen.getByText('角色')).toBeInTheDocument()
      expect(screen.getByText('积分')).toBeInTheDocument()
    })
  })
})

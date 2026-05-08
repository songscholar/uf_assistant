import { create } from 'zustand'
import { api } from '@/lib/api'

export interface User {
  id: number
  username: string
  email: string
  role: string
  nickname?: string
  avatar?: string
  credits?: number
  vip_plan?: string
}

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean

  login: (username: string, password: string) => Promise<void>
  loginWithCode: (email: string, code: string) => Promise<void>
  register: (username: string, email: string, password: string, code: string, referralCode?: string) => Promise<void>
  logout: () => void
  loadFromStorage: () => void
  fetchUserInfo: () => Promise<void>
}

// 初始化时从 localStorage 同步读取 token，避免刷新后 ProtectedRoute 先重定向
const _initToken = localStorage.getItem('token')

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: _initToken,
  isAuthenticated: !!_initToken,

  login: async (username, password) => {
    const resp = await api.post('/auth/login', { username, password })
    const { token, user } = resp.data
    localStorage.setItem('token', token)
    set({ token, user, isAuthenticated: true })
  },

  loginWithCode: async (email, code) => {
    const resp = await api.post('/auth/login-code', { email, code })
    const { token, user } = resp.data
    localStorage.setItem('token', token)
    set({ token, user, isAuthenticated: true })
  },

  register: async (username, email, password, code, referralCode?) => {
    const resp = await api.post('/auth/register', {
      username,
      email,
      password,
      code,
      referral_code: referralCode || undefined,
    })
    const { token, user } = resp.data
    localStorage.setItem('token', token)
    set({ token, user, isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem('token')
    set({ token: null, user: null, isAuthenticated: false })
  },

  loadFromStorage: () => {
    const token = localStorage.getItem('token')
    if (token) {
      set({ token, isAuthenticated: true })
      get().fetchUserInfo()
    }
  },

  fetchUserInfo: async () => {
    try {
      const resp = await api.get('/auth/info')
      set({ user: resp.data, isAuthenticated: true })
    } catch {
      get().logout()
    }
  },
}))

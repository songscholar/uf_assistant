import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from '@/components/layout/MainLayout'
import SettingsPanel from '@/components/settings/SettingsPanel'
import ChatPage from '@/pages/ChatPage'
import MarketPage from '@/pages/MarketPage'
import StockPage from '@/pages/StockPage'
import StrategyPage from '@/pages/StrategyPage'
import AnalysisPage from '@/pages/AnalysisPage'
import TradingPage from '@/pages/TradingPage'
import CryptoPage from '@/pages/CryptoPage'
import BillingPage from '@/pages/BillingPage'
import ProfilePage from '@/pages/ProfilePage'
import AdminUsersPage from '@/pages/AdminUsersPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ProtectedRoute from '@/components/auth/ProtectedRoute'
import RainCanvas from '@/components/effects/RainCanvas'
import { useThemeStore } from '@/stores/themeStore'
import { useAuthStore } from '@/stores/authStore'
import { useEffect } from 'react'

function ThemeInitializer() {
  const { theme } = useThemeStore()

  useEffect(() => {
    const html = document.documentElement
    html.classList.remove('dark', 'rain')

    if (theme === 'dark') {
      html.classList.add('dark')
    } else if (theme === 'rain') {
      html.classList.add('rain')
    }

    html.setAttribute('data-theme', theme)
  }, [theme])

  return null
}

export default function App() {
  const { theme } = useThemeStore()
  const { loadFromStorage } = useAuthStore()
  const isRain = theme === 'rain'

  useEffect(() => {
    // store 初始化时已同步读取 token，这里只需恢复用户信息
    loadFromStorage()
  }, [loadFromStorage])

  return (
    <BrowserRouter>
      <ThemeInitializer />
      <RainCanvas enabled={isRain} />
      {isRain && <div className="rain-vignette" />}
      <div className="relative z-10">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/market" element={<MarketPage />} />
            <Route path="/stock/:symbol" element={<StockPage />} />
            <Route path="/strategy" element={<StrategyPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/trading" element={<TradingPage />} />
            <Route path="/crypto" element={<CryptoPage />} />
            <Route path="/billing" element={<BillingPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/" element={<Navigate to="/chat" replace />} />
          </Route>
        </Routes>
      </div>
      <SettingsPanel />
    </BrowserRouter>
  )
}

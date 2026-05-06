import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from '@/components/layout/MainLayout'
import ChatPage from '@/pages/ChatPage'
import MarketPage from '@/pages/MarketPage'
import StockPage from '@/pages/StockPage'
import StrategyPage from '@/pages/StrategyPage'
import TradingPage from '@/pages/TradingPage'
import CryptoPage from '@/pages/CryptoPage'
import { useThemeStore } from '@/stores/themeStore'
import { useEffect } from 'react'

function ThemeInitializer() {
  const { theme } = useThemeStore()

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeInitializer />
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/stock/:symbol" element={<StockPage />} />
          <Route path="/strategy" element={<StrategyPage />} />
          <Route path="/trading" element={<TradingPage />} />
          <Route path="/crypto" element={<CryptoPage />} />
          <Route path="/" element={<Navigate to="/chat" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

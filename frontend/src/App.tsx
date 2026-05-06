import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from '@/components/layout/MainLayout'
import SettingsPanel from '@/components/settings/SettingsPanel'
import ChatPage from '@/pages/ChatPage'
import MarketPage from '@/pages/MarketPage'
import StockPage from '@/pages/StockPage'
import StrategyPage from '@/pages/StrategyPage'
import TradingPage from '@/pages/TradingPage'
import CryptoPage from '@/pages/CryptoPage'
import RainCanvas from '@/components/effects/RainCanvas'
import { useThemeStore } from '@/stores/themeStore'
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
  const isRain = theme === 'rain'

  return (
    <BrowserRouter>
      <ThemeInitializer />
      <RainCanvas enabled={isRain} />
      {isRain && <div className="rain-vignette" />}
      <div className="relative z-10">
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
      </div>
      <SettingsPanel />
    </BrowserRouter>
  )
}

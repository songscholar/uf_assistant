import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'
import { useIsDesktop, useIsTablet } from '@/hooks/useMediaQuery'
import { cn } from '@/lib/utils'

export default function MainLayout() {
  const location = useLocation()
  const isDesktop = useIsDesktop()
  const isTablet = useIsTablet()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const sidebarWidth = collapsed ? 72 : 260

  return (
    <div className="h-screen w-screen overflow-hidden flex bg-bg-primary">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      <div
        className="flex flex-col flex-1 h-full transition-all duration-300"
        style={{
          marginLeft: isDesktop ? sidebarWidth : 0,
        }}
      >
        <Header onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-hidden">
          <div className="h-full animate-fade-in-up" key={location.pathname}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

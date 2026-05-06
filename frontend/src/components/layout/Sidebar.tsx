import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  MessageSquare,
  TrendingUp,
  Brain,
  Wallet,
  Bitcoin,
  Plus,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  Trash2,
  CloudRain,
} from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { useThemeStore, getThemeLabel } from '@/stores/themeStore'
import { APP_NAME, NAV_ITEMS } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { Conversation } from '@/types'

const iconMap: Record<string, React.ElementType> = {
  MessageSquare,
  TrendingUp,
  Brain,
  Wallet,
  Bitcoin,
}

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  mobileOpen: boolean
  onMobileClose: () => void
}

export default function Sidebar({ collapsed, onToggle, mobileOpen, onMobileClose }: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { theme, toggleTheme } = useThemeStore()
  const {
    conversations,
    currentConversationId,
    loadConversations,
    createConversation,
    switchConversation,
    deleteConversation,
  } = useChatStore()

  const [hoveredConv, setHoveredConv] = useState<string | null>(null)

  useEffect(() => {
    loadConversations()
  }, [])

  const handleNewChat = () => {
    createConversation()
    navigate('/chat')
    onMobileClose()
  }

  const handleNavClick = (path: string) => {
    navigate(path)
    onMobileClose()
  }

  const handleConversationClick = (id: string) => {
    switchConversation(id)
    navigate('/chat')
    onMobileClose()
  }

  const groupedConversations = conversations.reduce(
    (acc, conv) => {
      const date = new Date(conv.updated_at)
      const now = new Date()
      const diff = now.getTime() - date.getTime()
      const days = Math.floor(diff / 86400000)

      let group = '更早'
      if (days === 0) group = '今日'
      else if (days === 1) group = '昨天'
      else if (days <= 7) group = '7天内'

      if (!acc[group]) acc[group] = []
      acc[group].push(conv)
      return acc
    },
    {} as Record<string, Conversation[]>
  )

  const groupOrder = ['今日', '昨天', '7天内', '更早']

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 md:hidden"
          onClick={onMobileClose}
        />
      )}

      <aside
        className={cn(
          'fixed left-0 top-0 h-full bg-bg-secondary border-r border-border z-50',
          'transition-all duration-300 ease-out',
          'flex flex-col',
          collapsed ? 'w-[72px]' : 'w-[260px]',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
          'md:translate-x-0'
        )}
      >
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-border shrink-0">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center shrink-0">
            <TrendingUp className="w-4 h-4 text-white" />
          </div>
          {!collapsed && (
            <span className="ml-3 font-semibold text-text-primary truncate">{APP_NAME}</span>
          )}
        </div>

        {/* New Chat Button */}
        <div className="p-3 shrink-0">
          <button
            onClick={handleNewChat}
            className={cn(
              'w-full flex items-center justify-center gap-2',
              'h-10 rounded-xl bg-accent text-white font-medium',
              'hover:bg-accent-light transition-smooth',
              'shadow-md hover:shadow-lg',
              collapsed && 'px-0'
            )}
          >
            <Plus className="w-4 h-4" />
            {!collapsed && <span>新建对话</span>}
          </button>
        </div>

        {/* Navigation */}
        <nav className="px-3 shrink-0">
          {NAV_ITEMS.map((item) => {
            const Icon = iconMap[item.icon] || MessageSquare
            const isActive = location.pathname.startsWith(item.path)
            return (
              <button
                key={item.path}
                onClick={() => handleNavClick(item.path)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 h-9 rounded-lg',
                  'text-sm transition-smooth mb-0.5',
                  isActive
                    ? 'bg-accent-bg text-accent font-medium'
                    : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </button>
            )
          })}
        </nav>

        {/* Conversation History */}
        {!collapsed && (
          <div className="flex-1 overflow-y-auto px-3 py-2 min-h-0">
            {groupOrder.map(
              (group) =>
                groupedConversations[group]?.length > 0 && (
                  <div key={group} className="mb-3">
                    <div className="px-3 py-1 text-xs text-text-tertiary font-medium">
                      {group}
                    </div>
                    {groupedConversations[group].map((conv) => (
                      <div
                        key={conv.id}
                        className="relative"
                        onMouseEnter={() => setHoveredConv(conv.id)}
                        onMouseLeave={() => setHoveredConv(null)}
                      >
                        <button
                          onClick={() => handleConversationClick(conv.id)}
                          className={cn(
                            'w-full flex items-center gap-2 px-3 py-2 rounded-lg',
                            'text-sm text-text-secondary transition-smooth',
                            currentConversationId === conv.id
                              ? 'bg-accent-bg text-text-primary border-l-[3px] border-accent'
                              : 'hover:bg-bg-hover hover:text-text-primary border-l-[3px] border-transparent'
                          )}
                        >
                          <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-60" />
                          <span className="truncate text-left flex-1">
                            {conv.title || '新对话'}
                          </span>
                        </button>
                        {hoveredConv === conv.id && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              deleteConversation(conv.id)
                            }}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md hover:bg-bg-active text-text-tertiary hover:text-danger transition-smooth"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )
            )}
          </div>
        )}

        {/* Bottom Actions */}
        <div className="p-3 border-t border-border shrink-0 space-y-1">
          <button
            onClick={toggleTheme}
            className={cn(
              'w-full flex items-center gap-3 px-3 h-9 rounded-lg',
              'text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-smooth'
            )}
            title="点击切换主题"
          >
            {theme === 'rain' ? (
              <CloudRain className="w-4 h-4 shrink-0 text-accent" />
            ) : (
              <Settings className="w-4 h-4 shrink-0" />
            )}
            {!collapsed && <span>{getThemeLabel(theme)}</span>}
          </button>
          <button
            className={cn(
              'w-full flex items-center gap-3 px-3 h-9 rounded-lg',
              'text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-smooth'
            )}
          >
            <HelpCircle className="w-4 h-4 shrink-0" />
            {!collapsed && <span>帮助</span>}
          </button>
        </div>

        {/* Collapse Toggle (Desktop only) */}
        <button
          onClick={onToggle}
          className="hidden md:flex absolute -right-3 top-20 w-6 h-6 rounded-full bg-bg-card border border-border shadow-md items-center justify-center hover:shadow-lg transition-smooth z-10"
        >
          {collapsed ? (
            <ChevronRight className="w-3 h-3 text-text-secondary" />
          ) : (
            <ChevronLeft className="w-3 h-3 text-text-secondary" />
          )}
        </button>
      </aside>
    </>
  )
}

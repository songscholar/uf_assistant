import { useLocation, useNavigate } from 'react-router-dom'
import { Menu, Share2, MoreHorizontal, Bot } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { cn } from '@/lib/utils'

interface HeaderProps {
  onMenuClick: () => void
}

const pageTitles: Record<string, string> = {
  '/chat': '对话',
  '/market': '市场行情',
  '/strategy': '策略与选股',
  '/trading': '模拟交易',
  '/crypto': '加密货币',
}

export default function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const { currentConversationId, messages } = useChatStore()

  const isChat = location.pathname.startsWith('/chat')
  const isStock = location.pathname.startsWith('/stock/')

  let title = pageTitles[location.pathname] || '优富助手'
  let subtitle = ''

  if (isChat && currentConversationId && messages.length > 0) {
    const firstUserMsg = messages.find((m) => m.role === 'user')
    title = firstUserMsg ? firstUserMsg.content.slice(0, 20) + '...' : '新对话'
    subtitle = '优富助手'
  }

  return (
    <header className="h-[52px] bg-bg-card/80 backdrop-blur-xl border-b border-border flex items-center justify-between px-4 sticky top-0 z-30 shrink-0">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="md:hidden p-2 rounded-lg hover:bg-bg-hover transition-smooth"
        >
          <Menu className="w-5 h-5 text-text-secondary" />
        </button>
        <div>
          <h1 className="text-sm font-semibold text-text-primary">{title}</h1>
          {subtitle && (
            <p className="text-xs text-text-tertiary">{subtitle}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1">
        <button className="p-2 rounded-lg hover:bg-bg-hover transition-smooth text-text-secondary">
          <Share2 className="w-4 h-4" />
        </button>
        <button className="p-2 rounded-lg hover:bg-bg-hover transition-smooth text-text-secondary">
          <MoreHorizontal className="w-4 h-4" />
        </button>
      </div>
    </header>
  )
}

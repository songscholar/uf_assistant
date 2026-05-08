import { useState, useRef, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Menu, Share2, MoreHorizontal, Settings, Copy, Check, MessageCircle, AtSign, LogOut, User } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { useRainStore } from '@/stores/rainStore'
import { useAuthStore } from '@/stores/authStore'
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
  const { togglePanel } = useRainStore()
  const { user, logout } = useAuthStore()

  const [shareOpen, setShareOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const shareRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (shareRef.current && !shareRef.current.contains(e.target as Node)) setShareOpen(false)
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const isChat = location.pathname.startsWith('/chat')

  let title = pageTitles[location.pathname] || '优富助手'
  let subtitle = ''

  if (isChat && currentConversationId && messages.length > 0) {
    const firstUserMsg = messages.find((m) => m.role === 'user')
    title = firstUserMsg ? firstUserMsg.content.slice(0, 20) + '...' : '新对话'
    subtitle = '优富助手'
  }

  const handleShare = async () => {
    const url = window.location.href
    const text = `${title} - UF Stock Assistant`
    if (navigator.share) {
      try {
        await navigator.share({ title, text, url })
        return
      } catch { /* fallback */ }
    }
    setShareOpen(true)
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* ignore */ }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
    setMenuOpen(false)
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

      <div className="flex items-center gap-1 relative">
        <button
          onClick={togglePanel}
          className="p-2 rounded-lg hover:bg-bg-hover transition-smooth text-text-secondary"
          title="设置"
        >
          <Settings className="w-4 h-4" />
        </button>

        {/* Share Button */}
        <div ref={shareRef} className="relative">
          <button
            onClick={handleShare}
            className="p-2 rounded-lg hover:bg-bg-hover transition-smooth text-text-secondary"
            title="分享"
          >
            <Share2 className="w-4 h-4" />
          </button>

          {shareOpen && (
            <div className="absolute right-0 top-full mt-2 w-56 rounded-xl bg-bg-card border border-border shadow-xl py-2 z-50">
              <div className="px-3 py-1.5 text-xs font-medium text-text-tertiary">分享到</div>
              <button
                onClick={handleCopy}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-bg-hover transition-colors"
              >
                {copied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
                {copied ? '已复制链接' : '复制链接'}
              </button>
              <button
                onClick={() => { handleCopy(); setShareOpen(false) }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-bg-hover transition-colors"
              >
                <MessageCircle className="w-4 h-4 text-green-500" />
                微信
              </button>
              <button
                onClick={() => { handleCopy(); setShareOpen(false) }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-bg-hover transition-colors"
              >
                <AtSign className="w-4 h-4 text-blue-500" />
                QQ
              </button>
            </div>
          )}
        </div>

        {/* More Menu */}
        <div ref={menuRef} className="relative">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-2 rounded-lg hover:bg-bg-hover transition-smooth text-text-secondary"
            title="更多"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-2 w-52 rounded-xl bg-bg-card border border-border shadow-xl py-1 z-50">
              {user && (
                <>
                  <div className="px-3 py-2 border-b border-border-light">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-xs font-medium">
                        {(user.nickname || user.username || '?')[0].toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-text-primary">{user.nickname || user.username}</p>
                        <p className="text-xs text-text-tertiary">{user.email}</p>
                      </div>
                    </div>
                  </div>
                  <div className="px-3 py-1 text-xs text-text-tertiary">
                    {user.role === 'admin' ? '管理员' : user.role === 'manager' ? '经理' : '用户'}
                    {user.credits !== undefined && ` · ${user.credits} 积分`}
                  </div>
                </>
              )}
              <button
                onClick={() => { navigate('/profile'); setMenuOpen(false) }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-bg-hover transition-colors"
              >
                <User className="w-4 h-4 text-text-secondary" />
                个人中心
              </button>
              <div className="border-t border-border-light my-1" />
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-danger hover:bg-danger-bg transition-colors"
              >
                <LogOut className="w-4 h-4" />
                退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

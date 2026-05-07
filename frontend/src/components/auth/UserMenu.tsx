import { useState, useRef, useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'

export default function UserMenu() {
  const { user, logout } = useAuthStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!user) return null

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors"
      >
        <div className="w-7 h-7 rounded-full bg-[var(--color-accent)] flex items-center justify-center text-white text-sm font-medium">
          {(user.nickname || user.username || '?')[0].toUpperCase()}
        </div>
        <span className="text-sm text-[var(--color-text)] hidden sm:inline">
          {user.nickname || user.username}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-48 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 z-50">
          <div className="px-3 py-2 border-b border-[var(--color-border)]">
            <p className="text-sm font-medium text-[var(--color-text)]">{user.nickname || user.username}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">{user.email}</p>
          </div>
          <div className="px-3 py-1.5 text-xs text-[var(--color-text-secondary)]">
            {user.role === 'admin' ? '管理员' : user.role === 'manager' ? '经理' : '用户'}
            {user.credits !== undefined && ` · ${user.credits} 积分`}
          </div>
          <button
            onClick={() => { logout(); setOpen(false) }}
            className="w-full text-left px-3 py-2 text-sm text-red-500 hover:bg-[var(--color-surface-hover)] transition-colors"
          >
            退出登录
          </button>
        </div>
      )}
    </div>
  )
}

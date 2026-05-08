import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/lib/api'

export default function RegisterPage() {
  const navigate = useNavigate()
  const { register } = useAuthStore()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [codeSent, setCodeSent] = useState(false)
  const [codeCooldown, setCodeCooldown] = useState(0)
  const [codeLoading, setCodeLoading] = useState(false)

  const sendCode = async () => {
    if (!email || codeLoading) return
    setCodeLoading(true)
    setError('')
    try {
      await api.post('/auth/send-code', { email, code_type: 'register' })
      setCodeSent(true)
      setCodeCooldown(60)
      const timer = setInterval(() => {
        setCodeCooldown(prev => {
          if (prev <= 1) { clearInterval(timer); return 0 }
          return prev - 1
        })
      }, 1000)
    } catch (err: any) {
      const msg = err.response?.data?.detail || (err instanceof Error ? err.message : '发送验证码失败')
      setError(msg)
    } finally {
      setCodeLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }
    setLoading(true)
    try {
      await register(username, email, password, code)
      navigate('/chat')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '注册失败'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)] px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[var(--color-text)]">注册账号</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">UF Stock Assistant</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-6 space-y-4">
          {error && (
            <div className="text-sm text-red-500 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">用户名</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              required
              minLength={3}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">邮箱</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="flex-1 px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                required
              />
              <button
                type="button"
                onClick={sendCode}
                disabled={codeCooldown > 0 || codeLoading}
                className="px-3 py-2 rounded-lg bg-[var(--color-accent)]/15 text-[var(--color-accent)] border border-[var(--color-accent)]/30 text-sm whitespace-nowrap font-medium
                           hover:bg-[var(--color-accent)]/25 hover:shadow-[0_0_12px_rgba(59,130,246,0.15)] hover:-translate-y-[1px]
                           active:scale-[0.985] active:bg-[var(--color-accent)]/35 active:translate-y-0
                           disabled:opacity-50 transition-all duration-200"
              >
                {codeLoading ? '发送中...' : codeCooldown > 0 ? `${codeCooldown}s` : '发送验证码'}
              </button>
            </div>
          </div>

          {codeSent && (
            <div>
              <label className="block text-sm font-medium text-[var(--color-text)] mb-1">验证码</label>
              <input
                type="text"
                value={code}
                onChange={e => setCode(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                required
                maxLength={6}
                placeholder="6位验证码"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              required
              minLength={8}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">确认密码</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading || !codeSent}
            className="w-full py-2.5 rounded-lg bg-[var(--color-accent)]/15 text-[var(--color-accent)] border border-[var(--color-accent)]/30 font-medium
                       hover:bg-[var(--color-accent)]/25 hover:shadow-[0_0_12px_rgba(59,130,246,0.15)] hover:-translate-y-[1px]
                       active:scale-[0.985] active:bg-[var(--color-accent)]/35 active:translate-y-0
                       disabled:opacity-50 transition-all duration-200"
          >
            {loading ? '注册中...' : '注册'}
          </button>

          <div className="text-sm text-center">
            <Link to="/login" className="text-[var(--color-accent)] hover:underline hover:opacity-80 transition-opacity">已有账号？登录</Link>
          </div>
        </form>
      </div>
    </div>
  )
}

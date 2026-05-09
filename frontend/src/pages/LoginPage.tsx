import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/chat')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '登录失败'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary px-4">
      <div className="w-full max-w-sm animate-fade-in-up">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-text-primary">UF Stock Assistant</h1>
          <p className="text-sm text-text-secondary mt-1">智能股票助手</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-bg-card rounded-xl border border-border p-6 space-y-4 animate-scale-in">
          {error && (
            <div className="text-sm text-danger bg-danger-bg rounded-lg px-3 py-2 animate-shake">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">用户名</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all duration-200"
              required
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all duration-200"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-accent/15 text-accent border border-accent/30 font-medium
                       hover:bg-accent/25 hover:shadow-[0_0_12px_rgba(200,85,61,0.15)] hover:-translate-y-[1px]
                       active:scale-[0.985] active:bg-accent/35 active:translate-y-0
                       disabled:opacity-50 transition-all duration-200"
          >
            {loading ? '登录中...' : '登录'}
          </button>

          <div className="flex items-center justify-between text-sm">
            <Link to="/register" className="text-accent hover:underline hover:opacity-80 transition-all duration-200">注册账号</Link>
          </div>
        </form>
      </div>
    </div>
  )
}

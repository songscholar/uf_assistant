import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { api, getErrorMessage } from '@/lib/api'

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
  const [devCode, setDevCode] = useState('')

  const sendCode = async () => {
    if (!email || codeLoading) return
    setCodeLoading(true)
    setError('')
    setDevCode('')
    try {
      const resp = await api.post('/auth/send-code', { email, code_type: 'register' })
      setCodeSent(true)
      setCodeCooldown(60)
      // dev_mode 下验证码记录在后端日志，需手动查看
      if (resp.data?.dev_mode) {
        setDevCode('开发模式：验证码已记录到后端日志，请查看运行后端服务的终端')
      }
      const timer = setInterval(() => {
        setCodeCooldown(prev => {
          if (prev <= 1) { clearInterval(timer); return 0 }
          return prev - 1
        })
      }, 1000)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      const msg = Array.isArray(detail)
        ? detail.map((d: any) => d.msg || String(d)).join('；')
        : (detail || getErrorMessage(err, '发送验证码失败'))
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
      setError(getErrorMessage(err, '注册失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary px-4">
      <div className="w-full max-w-sm animate-fade-in-up">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-text-primary">注册账号</h1>
          <p className="text-sm text-text-secondary mt-1">UF Stock Assistant</p>
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
              minLength={3}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">邮箱</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="flex-1 px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all duration-200"
                required
              />
              <button
                type="button"
                onClick={sendCode}
                disabled={codeCooldown > 0 || codeLoading}
                className="px-3 py-2 rounded-lg bg-accent/15 text-accent border border-accent/30 text-sm whitespace-nowrap font-medium
                           hover:bg-accent/25 hover:shadow-[0_0_12px_rgba(200,85,61,0.15)] hover:-translate-y-[1px]
                           active:scale-[0.985] active:bg-accent/35 active:translate-y-0
                           disabled:opacity-50 transition-all duration-200"
              >
                {codeLoading ? '发送中...' : codeCooldown > 0 ? `${codeCooldown}s` : '发送验证码'}
              </button>
            </div>
          </div>

          {devCode && (
            <div className="text-xs text-text-secondary bg-bg-secondary rounded-lg px-3 py-2">
              {devCode}
            </div>
          )}
          {codeSent && (
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">验证码</label>
              <input
                type="text"
                value={code}
                onChange={e => setCode(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all duration-200"
                required
                maxLength={6}
                placeholder="6位验证码"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all duration-200"
              required
              minLength={8}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">确认密码</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all duration-200"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading || !codeSent}
            className="w-full py-2.5 rounded-lg bg-accent/15 text-accent border border-accent/30 font-medium
                       hover:bg-accent/25 hover:shadow-[0_0_12px_rgba(200,85,61,0.15)] hover:-translate-y-[1px]
                       active:scale-[0.985] active:bg-accent/35 active:translate-y-0
                       disabled:opacity-50 transition-all duration-200"
          >
            {loading ? '注册中...' : '注册'}
          </button>

          <div className="text-sm text-center">
            <Link to="/login" className="text-accent hover:underline hover:opacity-80 transition-all duration-200">已有账号？登录</Link>
          </div>
        </form>
      </div>
    </div>
  )
}

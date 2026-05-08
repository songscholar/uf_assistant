import { useState, useEffect } from 'react'
import {
  User,
  Mail,
  Calendar,
  Bell,
  BarChart3,
  Save,
  Pencil,
  Trash2,
  Plus,
  Shield,
  Settings,
  ChevronRight,
} from 'lucide-react'
import { userApi } from '@/lib/api'
import type { UserProfile, NotificationSettings, ChartTemplate } from '@/types'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { useNavigate } from 'react-router-dom'

// ── Toggle Switch ───────────────────────────────────────────────────────────

function Toggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        'relative w-11 h-6 rounded-full transition-colors duration-200',
        enabled ? 'bg-accent' : 'bg-bg-secondary'
      )}
    >
      <div className={cn(
        'absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200',
        enabled ? 'translate-x-[22px]' : 'translate-x-0.5'
      )} />
    </button>
  )
}

// ── Profile Section ─────────────────────────────────────────────────────────

function ProfileSection() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ username: '', email: '' })
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    userApi.getProfile()
      .then((res) => {
        const data = res.data?.data || res.data || {}
        setProfile(data)
        setForm({ username: data.username || '', email: data.email || '' })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await userApi.updateProfile(form)
      setProfile((prev) => prev ? { ...prev, ...form } : null)
      setEditing(false)
    } catch { /* silent */ }
    finally { setSaving(false) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-32 text-text-tertiary text-sm">加载中...</div>
  }

  return (
    <div className="bg-bg-card border border-border rounded-xl p-6 card-hover">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
          <User className="w-5 h-5 text-accent" />
          个人信息
        </h3>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="p-2 rounded-lg hover:bg-bg-hover text-text-secondary hover:text-accent transition-all"
          >
            <Pencil className="w-4 h-4" />
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-4">
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">用户名</label>
            <input
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">邮箱</label>
            <input
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                'bg-accent text-white hover:bg-accent-light',
                'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                'disabled:opacity-50 flex items-center gap-1.5'
              )}
            >
              <Save className="w-3.5 h-3.5" />
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              onClick={() => { setEditing(false); setForm({ username: profile?.username || '', email: profile?.email || '' }) }}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-bg-secondary text-text-secondary hover:bg-bg-hover transition-all"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-accent-bg flex items-center justify-center">
              <User className="w-6 h-6 text-accent" />
            </div>
            <div>
              <div className="font-semibold text-text-primary">{profile?.username || '--'}</div>
              <div className="text-sm text-text-secondary">{profile?.email || '--'}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            <Calendar className="w-3.5 h-3.5" />
            注册时间: {profile?.created_at ? new Date(profile.created_at).toLocaleDateString('zh-CN') : '--'}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Notification Settings ───────────────────────────────────────────────────

function NotificationSection() {
  const [settings, setSettings] = useState<NotificationSettings>({
    email_enabled: false,
    telegram_enabled: false,
    browser_enabled: true,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    userApi.getNotificationSettings()
      .then((res) => {
        const data = res.data?.data || res.data || {}
        if (data.email_enabled !== undefined) setSettings(data)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const toggle = async (key: keyof NotificationSettings) => {
    const newSettings = { ...settings, [key]: !settings[key] }
    setSettings(newSettings)
    try {
      await userApi.updateNotificationSettings(newSettings)
    } catch {
      // Revert on error
      setSettings(settings)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-24 text-text-tertiary text-sm">加载中...</div>
  }

  return (
    <div className="bg-bg-card border border-border rounded-xl p-6 card-hover">
      <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Bell className="w-5 h-5 text-accent" />
        通知设置
      </h3>
      <div className="space-y-4">
        {[
          { key: 'email_enabled' as const, label: '邮件通知', desc: '接收交易信号和系统通知的邮件' },
          { key: 'telegram_enabled' as const, label: 'Telegram 通知', desc: '通过 Telegram Bot 接收实时通知' },
          { key: 'browser_enabled' as const, label: '浏览器通知', desc: '在浏览器中接收推送通知' },
        ].map((item) => (
          <div key={item.key} className="flex items-center justify-between py-2">
            <div>
              <div className="text-sm font-medium text-text-primary">{item.label}</div>
              <div className="text-xs text-text-tertiary">{item.desc}</div>
            </div>
            <Toggle enabled={settings[item.key]} onToggle={() => toggle(item.key)} />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Chart Templates ─────────────────────────────────────────────────────────

function ChartTemplatesSection() {
  const [templates, setTemplates] = useState<ChartTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newName, setNewName] = useState('')

  useEffect(() => {
    userApi.getChartTemplates()
      .then((res) => {
        const data = res.data?.data || res.data || {}
        setTemplates(data.templates || data || [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const res = await userApi.createChartTemplate({ name: newName, config: {}, is_default: false })
      const created = res.data?.data || res.data
      if (created) setTemplates((prev) => [...prev, created])
      setNewName('')
      setShowAdd(false)
    } catch { /* silent */ }
  }

  const handleDelete = async (id: string) => {
    try {
      await userApi.deleteChartTemplate(id)
      setTemplates((prev) => prev.filter((t) => t.id !== id))
    } catch { /* silent */ }
  }

  const handleSetDefault = async (id: string) => {
    try {
      await userApi.updateChartTemplate(id, { is_default: true })
      setTemplates((prev) => prev.map((t) => ({ ...t, is_default: t.id === id })))
    } catch { /* silent */ }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-24 text-text-tertiary text-sm">加载中...</div>
  }

  return (
    <div className="bg-bg-card border border-border rounded-xl p-6 card-hover">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-accent" />
          图表模板
        </h3>
        <button
          onClick={() => setShowAdd(true)}
          className={cn(
            'px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200',
            'bg-accent text-white hover:bg-accent-light',
            'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
            'flex items-center gap-1 shadow-sm'
          )}
        >
          <Plus className="w-3.5 h-3.5" />
          新建
        </button>
      </div>

      {showAdd && (
        <div className="flex items-center gap-2 mb-4 p-3 rounded-lg bg-bg-secondary border border-border">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="模板名称"
            className="flex-1 px-3 py-1.5 rounded-lg bg-bg-card border border-border text-text-primary text-sm"
            autoFocus
          />
          <button onClick={handleCreate} className="px-3 py-1.5 rounded-lg bg-accent text-white text-sm">确定</button>
          <button onClick={() => { setShowAdd(false); setNewName('') }} className="px-3 py-1.5 rounded-lg bg-bg-card text-text-secondary text-sm">取消</button>
        </div>
      )}

      {templates.length === 0 ? (
        <div className="text-center py-8 text-text-tertiary text-sm">
          <BarChart3 className="w-10 h-10 mx-auto mb-2 opacity-30" />
          暂无图表模板
        </div>
      ) : (
        <div className="space-y-2">
          {templates.map((t) => (
            <div key={t.id} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-bg-hover transition-colors">
              <div className="flex items-center gap-2">
                <span className="text-sm text-text-primary">{t.name}</span>
                {t.is_default && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-accent-bg text-accent">默认</span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {!t.is_default && (
                  <button
                    onClick={() => handleSetDefault(t.id)}
                    className="p-1 rounded hover:bg-bg-active text-text-tertiary hover:text-accent transition-all text-xs"
                    title="设为默认"
                  >
                    <Shield className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  onClick={() => handleDelete(t.id)}
                  className="p-1 rounded hover:bg-bg-active text-text-tertiary hover:text-danger transition-all"
                  title="删除"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin'

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        <ProfileSection />
        <NotificationSection />
        <ChartTemplatesSection />

        {/* Admin Link */}
        {isAdmin && (
          <button
            onClick={() => navigate('/admin/users')}
            className={cn(
              'w-full bg-bg-card border border-border rounded-xl p-4 card-hover',
              'flex items-center justify-between group'
            )}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-accent-bg flex items-center justify-center">
                <Settings className="w-5 h-5 text-accent" />
              </div>
              <div className="text-left">
                <div className="text-sm font-semibold text-text-primary">用户管理</div>
                <div className="text-xs text-text-tertiary">管理用户、角色和积分</div>
              </div>
            </div>
            <ChevronRight className="w-5 h-5 text-text-tertiary group-hover:text-accent transition-colors" />
          </button>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useCallback } from 'react'
import {
  Users,
  Search,
  Plus,
  Pencil,
  Trash2,
  Crown,
  Shield,
  X,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  UserPlus,
  Coins,
} from 'lucide-react'
import { userAdminApi, getErrorMessage } from '@/lib/api'
import type { AdminUser } from '@/types'
import { cn } from '@/lib/utils'

// ── Role Badge ──────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  return (
    <span className={cn(
      'px-2 py-0.5 rounded-md text-xs font-medium',
      role === 'admin' && 'bg-accent-bg text-accent',
      role === 'manager' && 'bg-[rgba(251,191,36,0.15)] text-amber-500',
      role === 'user' && 'bg-bg-secondary text-text-secondary',
      role === 'viewer' && 'bg-bg-secondary text-text-tertiary',
      !['admin', 'manager', 'user', 'viewer'].includes(role) && 'bg-bg-secondary text-text-tertiary'
    )}>
      {role}
    </span>
  )
}

// ── User Modal ──────────────────────────────────────────────────────────────

interface UserModalProps {
  user?: AdminUser | null
  onClose: () => void
  onSaved: () => void
}

function UserModal({ user, onClose, onSaved }: UserModalProps) {
  const [form, setForm] = useState({
    username: user?.username || '',
    email: user?.email || '',
    password: '',
    role: user?.role || 'user',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const isEdit = !!user

  const handleSave = async () => {
    if (!form.username || !form.email || (!isEdit && !form.password)) {
      setError('请填写所有必填字段')
      return
    }
    setSaving(true)
    setError('')
    try {
      if (isEdit && user) {
        const updateData: Record<string, unknown> = { username: form.username, email: form.email, role: form.role }
        if (form.password) updateData.password = form.password
        await userAdminApi.updateUser(user.id, updateData)
      } else {
        await userAdminApi.createUser(form)
      }
      onSaved()
    } catch (err: unknown) {
      setError(getErrorMessage(err, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-bg-card border border-border rounded-xl w-full max-w-md p-6 shadow-xl animate-fade-in-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-text-primary">
            {isEdit ? '编辑用户' : '新建用户'}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-bg-hover text-text-secondary">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">用户名 *</label>
            <input
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">邮箱 *</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">密码 {isEdit ? '(留空不修改)' : '*'}</label>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              placeholder={isEdit ? '留空则不修改' : ''}
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">角色</label>
            <div className="flex gap-2">
              {['viewer', 'user', 'manager', 'admin'].map((r) => (
                <button
                  key={r}
                  onClick={() => setForm((f) => ({ ...f, role: r }))}
                  className={cn(
                    'flex-1 py-1.5 rounded-lg text-xs font-medium transition-all duration-200',
                    form.role === r
                      ? 'bg-accent text-white'
                      : 'bg-bg-secondary text-text-secondary hover:bg-bg-hover'
                  )}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-danger-bg border border-danger/20 text-danger text-xs">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-bg-secondary text-text-secondary text-sm hover:bg-bg-hover transition-all"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className={cn(
              'px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium',
              'hover:bg-accent-light transition-all duration-200',
              'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
              'disabled:opacity-50'
            )}
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Credits Modal ───────────────────────────────────────────────────────────

function CreditsModal({ user, onClose, onSaved }: { user: AdminUser; onClose: () => void; onSaved: () => void }) {
  const [credits, setCredits] = useState(String(user.credits))
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await userAdminApi.setCredits(user.id, parseInt(credits) || 0)
      onSaved()
    } catch { /* silent */ }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-bg-card border border-border rounded-xl w-full max-w-sm p-6 shadow-xl animate-fade-in-up" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-text-primary mb-4">设置积分 - {user.username}</h3>
        <div>
          <label className="text-xs text-text-tertiary mb-1 block">积分数量</label>
          <input
            type="number"
            value={credits}
            onChange={(e) => setCredits(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm"
          />
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-bg-secondary text-text-secondary text-sm hover:bg-bg-hover">取消</button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-light disabled:opacity-50"
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [stats, setStats] = useState<{ total: number; vip: number; active_today: number } | null>(null)

  // Modals
  const [showUserModal, setShowUserModal] = useState(false)
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null)
  const [creditsUser, setCreditsUser] = useState<AdminUser | null>(null)

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const [usersRes, statsRes] = await Promise.all([
        userAdminApi.listUsers({ page, limit: 20, role: roleFilter || undefined }).catch(() => ({ data: { data: { items: [], total: 0 } } })),
        userAdminApi.getStats().catch(() => ({ data: { data: {} } })),
      ])
      const usersData = usersRes.data?.data || usersRes.data || {}
      setUsers(usersData.items || usersData.users || [])
      setTotalPages(Math.max(1, Math.ceil((usersData.total || 0) / 20)))

      const statsData = statsRes.data?.data || statsRes.data || {}
      if (statsData.total_users !== undefined || statsData.total !== undefined) {
        setStats({
          total: statsData.total_users || statsData.total || 0,
          vip: statsData.vip_users || statsData.vip || 0,
          active_today: statsData.active_today || 0,
        })
      }
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [page, roleFilter])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除该用户？此操作不可撤销。')) return
    try {
      await userAdminApi.deleteUser(id)
      setUsers((prev) => prev.filter((u) => u.id !== id))
    } catch { /* silent */ }
  }

  const handleToggleVip = async (user: AdminUser) => {
    try {
      await userAdminApi.setVip(user.id, !user.is_vip)
      setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, is_vip: !u.is_vip } : u))
    } catch { /* silent */ }
  }

  const filteredUsers = search
    ? users.filter((u) => u.username.includes(search) || u.email.includes(search))
    : users

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Stats Cards */}
      {stats && (
        <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
          {[
            { label: '总用户数', value: stats.total.toLocaleString(), icon: Users },
            { label: 'VIP 用户', value: stats.vip.toLocaleString(), icon: Crown },
            { label: '今日活跃', value: stats.active_today.toLocaleString(), icon: Shield },
          ].map((item) => (
            <div key={item.label} className="bg-bg-card border border-border rounded-xl p-4 card-hover">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg bg-accent-bg flex items-center justify-center">
                  <item.icon className="w-4 h-4 text-accent" />
                </div>
                <span className="text-xs text-text-tertiary">{item.label}</span>
              </div>
              <div className="text-xl font-bold text-text-primary">{item.value}</div>
            </div>
          ))}
        </section>
      )}

      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索用户名或邮箱..."
              className="pl-9 pr-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm w-64 transition-all duration-200 hover:border-border-focus focus:border-accent"
            />
          </div>
          <div className="flex bg-bg-secondary rounded-lg p-0.5">
            {[
              { key: '', label: '全部' },
              { key: 'admin', label: '管理员' },
              { key: 'user', label: '用户' },
              { key: 'viewer', label: '观察者' },
            ].map((r) => (
              <button
                key={r.key}
                onClick={() => { setRoleFilter(r.key); setPage(1) }}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200',
                  roleFilter === r.key
                    ? 'bg-bg-card text-accent shadow-sm'
                    : 'text-text-secondary hover:text-text-primary'
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={() => { setEditingUser(null); setShowUserModal(true) }}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
            'bg-accent text-white hover:bg-accent-light',
            'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
            'flex items-center gap-1.5 shadow-sm'
          )}
        >
          <UserPlus className="w-4 h-4" />
          新建用户
        </button>
      </div>

      {/* Users Table */}
      <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg-secondary text-text-secondary text-xs">
              {['用户名', '邮箱', '角色', '积分', 'VIP', '注册时间', '最后登录', '操作'].map((h) => (
                <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-text-tertiary text-sm">加载中...</td></tr>
            ) : filteredUsers.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-text-tertiary text-sm">
                  <Users className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  暂无用户
                </td>
              </tr>
            ) : (
              filteredUsers.map((user) => (
                <tr key={user.id} className="hover:bg-bg-hover transition-colors duration-150">
                  <td className="px-4 py-3 text-text-primary font-medium">{user.username}</td>
                  <td className="px-4 py-3 text-text-secondary text-xs">{user.email}</td>
                  <td className="px-4 py-3"><RoleBadge role={user.role} /></td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setCreditsUser(user)}
                      className="text-text-primary hover:text-accent transition-colors font-medium"
                    >
                      {user.credits}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggleVip(user)}
                      className={cn(
                        'px-2 py-0.5 rounded text-xs font-medium transition-all',
                        user.is_vip
                          ? 'bg-[rgba(251,191,36,0.15)] text-amber-500'
                          : 'bg-bg-secondary text-text-tertiary hover:text-text-secondary'
                      )}
                    >
                      {user.is_vip ? 'VIP' : '--'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-text-tertiary text-xs whitespace-nowrap">
                    {user.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : '--'}
                  </td>
                  <td className="px-4 py-3 text-text-tertiary text-xs whitespace-nowrap">
                    {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString('zh-CN') : '--'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => { setEditingUser(user); setShowUserModal(true) }}
                        className="p-1.5 rounded-lg hover:bg-bg-hover text-text-secondary hover:text-accent transition-all"
                        title="编辑"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(user.id)}
                        className="p-1.5 rounded-lg hover:bg-bg-hover text-text-secondary hover:text-danger transition-all"
                        title="删除"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="p-2 rounded-lg bg-bg-card border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-40 transition-all"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-sm text-text-secondary px-3">{page} / {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="p-2 rounded-lg bg-bg-card border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-40 transition-all"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Modals */}
      {showUserModal && (
        <UserModal
          user={editingUser}
          onClose={() => { setShowUserModal(false); setEditingUser(null) }}
          onSaved={() => { setShowUserModal(false); setEditingUser(null); fetchUsers() }}
        />
      )}
      {creditsUser && (
        <CreditsModal
          user={creditsUser}
          onClose={() => setCreditsUser(null)}
          onSaved={() => { setCreditsUser(null); fetchUsers() }}
        />
      )}
    </div>
  )
}

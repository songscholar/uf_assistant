import { useState, useEffect, useCallback } from 'react'
import {
  Crown,
  Check,
  Coins,
  CreditCard,
  History,
  Wallet,
  Copy,
  CheckCircle,
  Clock,
  AlertCircle,
} from 'lucide-react'
import { billingApi } from '@/lib/api'
import type { BillingPlan, CreditBalance, CreditLog, MembershipInfo } from '@/types'
import { cn, formatNumber } from '@/lib/utils'

type BillingTab = 'plans' | 'credits' | 'recharge'

const TABS = [
  { key: 'plans' as const, label: '会员套餐', icon: Crown },
  { key: 'credits' as const, label: '积分', icon: Coins },
  { key: 'recharge' as const, label: '充值', icon: CreditCard },
]

// ── Plans Tab ───────────────────────────────────────────────────────────────

function PlansTab() {
  const [plans, setPlans] = useState<BillingPlan[]>([])
  const [membership, setMembership] = useState<MembershipInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [subscribing, setSubscribing] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      billingApi.getPlans().catch(() => ({ data: { data: { plans: [] } } })),
      billingApi.getMembership().catch(() => ({ data: { data: null } })),
    ]).then(([plansRes, memRes]) => {
      const plansData = plansRes.data?.data || plansRes.data || {}
      setPlans(plansData.plans || plansData || [])
      setMembership(memRes.data?.data || memRes.data || null)
    }).finally(() => setLoading(false))
  }, [])

  const handleSubscribe = async (planId: string) => {
    setSubscribing(planId)
    try {
      await billingApi.subscribe(planId)
      // Refresh membership
      const res = await billingApi.getMembership()
      setMembership(res.data?.data || res.data || null)
    } catch { /* silent */ }
    finally { setSubscribing(null) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40 text-text-tertiary text-sm">加载中...</div>
  }

  // Default plans if API returns empty
  const displayPlans: BillingPlan[] = plans.length > 0 ? plans : [
    { id: 'free', name: '免费版', price: 0, credits: 100, features: ['每日 5 次 AI 分析', '基础策略回测', '模拟交易'] },
    { id: 'pro', name: '专业版', price: 99, credits: 5000, features: ['无限 AI 分析', '高级策略回测', '实盘交易', '优先客服'], popular: true },
    { id: 'enterprise', name: '企业版', price: 299, credits: 20000, features: ['全部功能', 'API 接口', '专属客服', '定制策略'] },
  ]

  return (
    <div className="space-y-6">
      {/* Current Membership */}
      {membership && (
        <div className="bg-bg-card border border-border rounded-xl p-4 card-hover">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-accent-bg flex items-center justify-center">
              <Crown className="w-5 h-5 text-accent" />
            </div>
            <div>
              <div className="text-sm font-semibold text-text-primary">当前会员: {membership.level}</div>
              <div className="text-xs text-text-tertiary">
                到期时间: {membership.expires_at ? new Date(membership.expires_at).toLocaleDateString('zh-CN') : '永久'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Plans Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {displayPlans.map((plan) => (
          <div
            key={plan.id}
            className={cn(
              'bg-bg-card border rounded-xl p-6 card-hover relative overflow-hidden',
              plan.popular ? 'border-accent' : 'border-border'
            )}
          >
            {plan.popular && (
              <div className="absolute top-3 right-3 px-2 py-0.5 rounded-full bg-accent-bg text-accent text-xs font-medium">
                推荐
              </div>
            )}
            <h3 className="text-lg font-bold text-text-primary mb-1">{plan.name}</h3>
            <div className="mb-4">
              <span className="text-3xl font-bold text-text-primary">{plan.price === 0 ? '免费' : `¥${plan.price}`}</span>
              {plan.price > 0 && <span className="text-sm text-text-secondary">/月</span>}
            </div>
            <div className="text-xs text-text-tertiary mb-4">赠送 {plan.credits} 积分</div>
            <ul className="space-y-2 mb-6">
              {plan.features.map((f) => (
                <li key={f} className="text-sm text-text-secondary flex items-center gap-2">
                  <Check className="w-4 h-4 text-success shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
            <button
              onClick={() => handleSubscribe(plan.id)}
              disabled={subscribing === plan.id || plan.price === 0}
              className={cn(
                'w-full py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                'disabled:opacity-50',
                plan.popular
                  ? 'bg-accent text-white hover:bg-accent-light shadow-sm'
                  : 'bg-bg-secondary text-text-primary hover:bg-bg-hover'
              )}
            >
              {subscribing === plan.id ? '处理中...' : plan.price === 0 ? '当前方案' : '订阅'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Credits Tab ─────────────────────────────────────────────────────────────

function CreditsTab() {
  const [balance, setBalance] = useState<CreditBalance | null>(null)
  const [logs, setLogs] = useState<CreditLog[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [balRes, logRes] = await Promise.all([
        billingApi.getCredits().catch(() => ({ data: { data: {} } })),
        billingApi.getCreditsLog({ page, limit: 20 }).catch(() => ({ data: { data: { items: [], total: 0 } } })),
      ])
      setBalance(balRes.data?.data || balRes.data || null)
      const logData = logRes.data?.data || logRes.data || {}
      setLogs(logData.items || logData.logs || [])
      setTotalPages(Math.max(1, Math.ceil((logData.total || 0) / 20)))
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [page])

  useEffect(() => { fetchData() }, [fetchData])

  return (
    <div className="space-y-6">
      {/* Balance Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label: '当前余额', value: balance?.balance?.toLocaleString() ?? '--', icon: Coins, color: 'text-accent' },
          { label: '累计获得', value: balance?.total_earned?.toLocaleString() ?? '--', icon: CheckCircle, color: 'text-success' },
          { label: '累计消费', value: balance?.total_spent?.toLocaleString() ?? '--', icon: Wallet, color: 'text-text-secondary' },
        ].map((item) => (
          <div key={item.label} className="bg-bg-card border border-border rounded-xl p-4 card-hover">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-accent-bg flex items-center justify-center">
                <item.icon className="w-4 h-4 text-accent" />
              </div>
              <span className="text-xs text-text-tertiary">{item.label}</span>
            </div>
            <div className={cn('text-xl font-bold', item.color)}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* Credits Log Table */}
      <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg-secondary text-text-secondary text-xs">
              {['时间', '类型', '积分', '描述'].map((h) => (
                <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">
            {loading ? (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">加载中...</td></tr>
            ) : logs.length === 0 ? (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">暂无积分记录</td></tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="hover:bg-bg-hover transition-colors duration-150">
                  <td className="px-4 py-3 text-text-secondary text-xs">
                    {log.created_at ? new Date(log.created_at).toLocaleString('zh-CN') : '--'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      log.amount > 0 ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                    )}>
                      {log.type}
                    </span>
                  </td>
                  <td className={cn('px-4 py-3 text-right font-medium', log.amount > 0 ? 'text-success' : 'text-danger')}>
                    {log.amount > 0 ? '+' : ''}{log.amount}
                  </td>
                  <td className="px-4 py-3 text-text-secondary text-xs">{log.description}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
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
    </div>
  )
}

// ── Recharge Tab ────────────────────────────────────────────────────────────

function RechargeTab() {
  const [amount, setAmount] = useState('')
  const [payment, setPayment] = useState<{ address: string; amount: number; status: string } | null>(null)
  const [creating, setCreating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  const handleCreate = async () => {
    if (!amount || parseFloat(amount) <= 0) return
    setCreating(true)
    setError('')
    try {
      const res = await billingApi.createUsdtPayment(parseFloat(amount))
      setPayment(res.data?.data || res.data || null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '创建支付失败')
    } finally {
      setCreating(false)
    }
  }

  const handleCopy = () => {
    if (payment?.address) {
      navigator.clipboard.writeText(payment.address)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="max-w-md space-y-6">
      <div className="bg-bg-card border border-border rounded-xl p-6 card-hover">
        <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
          <CreditCard className="w-5 h-5 text-accent" />
          USDT 充值
        </h3>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">充值金额 (USDT)</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="请输入金额"
              min="1"
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
            />
          </div>
          <button
            onClick={handleCreate}
            disabled={creating || !amount}
            className={cn(
              'w-full py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
              'bg-accent text-white hover:bg-accent-light',
              'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
              'disabled:opacity-50 flex items-center justify-center gap-1.5 shadow-sm'
            )}
          >
            {creating ? <Clock className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
            {creating ? '创建中...' : '创建支付'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-danger-bg border border-danger/20 text-danger text-sm">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      {payment && (
        <div className="bg-bg-card border border-border rounded-xl p-6 card-hover animate-fade-in-up">
          <h4 className="text-sm font-semibold text-text-primary mb-4">请向以下地址转账</h4>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-text-tertiary mb-1">金额</div>
              <div className="text-xl font-bold text-accent">{payment.amount} USDT</div>
            </div>
            <div>
              <div className="text-xs text-text-tertiary mb-1">收款地址 (TRC-20)</div>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 rounded-lg bg-bg-secondary border border-border text-xs text-text-primary font-mono break-all">
                  {payment.address}
                </code>
                <button
                  onClick={handleCopy}
                  className="p-2 rounded-lg bg-bg-secondary border border-border text-text-secondary hover:text-accent transition-all"
                >
                  {copied ? <CheckCircle className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div className="flex items-start gap-2 p-3 rounded-lg bg-accent-bg/50 text-accent text-xs">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>请在 30 分钟内完成转账，系统将自动确认并充值积分。</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Chevron icons for pagination ────────────────────────────────────────────

function ChevronLeft(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m15 18-6-6 6-6" />
    </svg>
  )
}

function ChevronRight(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m9 18 6-6-6-6" />
    </svg>
  )
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function BillingPage() {
  const [activeTab, setActiveTab] = useState<BillingTab>('plans')

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Tab Bar */}
      <div className="flex items-center gap-1 mb-4 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-all duration-200',
              activeTab === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            )}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'plans' && <PlansTab />}
      {activeTab === 'credits' && <CreditsTab />}
      {activeTab === 'recharge' && <RechargeTab />}
    </div>
  )
}

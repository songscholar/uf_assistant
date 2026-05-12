import { useState, useEffect, useCallback, useRef } from 'react'
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
  X,
  QrCode,
  Smartphone,
  Zap,
} from 'lucide-react'
import { billingApi, getErrorMessage } from '@/lib/api'
import type { BillingPlan, CreditBalance, CreditLog, MembershipInfo, CnPayOrder } from '@/types'
import { cn, formatNumber } from '@/lib/utils'

type BillingTab = 'plans' | 'credits' | 'recharge'

const TABS = [
  { key: 'plans' as const, label: '会员套餐', icon: Crown },
  { key: 'credits' as const, label: '积分', icon: Coins },
  { key: 'recharge' as const, label: '充值', icon: CreditCard },
]

// ── Payment Channel Selector Modal ───────────────────────────────────────────

interface PaymentModalProps {
  plan: BillingPlan
  onClose: () => void
  onSuccess: () => void
}

function PaymentModal({ plan, onClose, onSuccess }: PaymentModalProps) {
  const [channel, setChannel] = useState<'mock' | 'alipay' | 'wechat'>('mock')
  const [order, setOrder] = useState<CnPayOrder | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const planMap: Record<string, string> = {
    free: 'free',
    pro: 'monthly',
    enterprise: 'yearly',
    lifetime: 'lifetime',
  }

  const createOrder = async (selectedChannel: 'mock' | 'alipay' | 'wechat') => {
    setLoading(true)
    setError('')
    try {
      const res = await billingApi.subscribe(planMap[plan.id] || plan.id, selectedChannel)
      const data = res.data?.data || res.data
      if (data) {
        setOrder(data)
        // 如果是模拟支付，不需要轮询；真实支付轮询状态
        if (selectedChannel !== 'mock' && data.order_id) {
          startPolling(data.order_id)
        }
      } else {
        setError('创建订单失败')
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { message?: string; detail?: string } } }
      setError(e.response?.data?.message || e.response?.data?.detail || '创建订单失败')
    } finally {
      setLoading(false)
    }
  }

  const startPolling = (orderId: number) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await billingApi.getPayOrder(orderId)
        const data = res.data?.data || res.data
        if (data?.status === 'paid') {
          if (pollRef.current) clearInterval(pollRef.current)
          setOrder((prev) => (prev ? { ...prev, status: 'paid' } : prev))
          onSuccess()
        }
      } catch { /* silent */ }
    }, 3000)
  }

  const handleMockConfirm = async () => {
    if (!order) return
    setConfirming(true)
    try {
      await billingApi.mockConfirm(order.order_id)
      setOrder((prev) => (prev ? { ...prev, status: 'paid' } : prev))
      onSuccess()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { message?: string; detail?: string } } }
      setError(e.response?.data?.message || e.response?.data?.detail || '支付确认失败')
    } finally {
      setConfirming(false)
    }
  }

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-bg-card border border-border rounded-2xl w-full max-w-md overflow-hidden animate-fade-in-up shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h3 className="text-base font-semibold text-text-primary">支付订阅</h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Plan Summary */}
          <div className="bg-accent-bg/50 rounded-xl p-4">
            <div className="text-sm text-text-secondary mb-1">{plan.name}</div>
            <div className="text-2xl font-bold text-text-primary">
              {plan.price === 0 ? '免费' : `¥${plan.price}`}
            </div>
            <div className="text-xs text-text-tertiary mt-1">赠送 {plan.credits} 积分</div>
          </div>

          {/* Channel Selection */}
          {!order && (
            <div className="space-y-3">
              <div className="text-xs text-text-tertiary font-medium">选择支付方式</div>
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={() => setChannel('mock')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all',
                    channel === 'mock'
                      ? 'border-accent bg-accent-bg text-accent'
                      : 'border-border bg-bg-secondary text-text-secondary hover:border-border-focus'
                  )}
                >
                  <Zap className="w-5 h-5" />
                  <span className="text-xs font-medium">模拟支付</span>
                </button>
                <button
                  onClick={() => setChannel('alipay')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all',
                    channel === 'alipay'
                      ? 'border-accent bg-accent-bg text-accent'
                      : 'border-border bg-bg-secondary text-text-secondary hover:border-border-focus'
                  )}
                >
                  <QrCode className="w-5 h-5" />
                  <span className="text-xs font-medium">支付宝</span>
                </button>
                <button
                  onClick={() => setChannel('wechat')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all',
                    channel === 'wechat'
                      ? 'border-accent bg-accent-bg text-accent'
                      : 'border-border bg-bg-secondary text-text-secondary hover:border-border-focus'
                  )}
                >
                  <Smartphone className="w-5 h-5" />
                  <span className="text-xs font-medium">微信支付</span>
                </button>
              </div>

              <button
                onClick={() => createOrder(channel)}
                disabled={loading}
                className={cn(
                  'w-full py-2.5 rounded-lg text-sm font-medium transition-all',
                  'bg-accent text-white hover:bg-accent-light',
                  'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                  'disabled:opacity-50 flex items-center justify-center gap-1.5 shadow-sm'
                )}
              >
                {loading ? <Clock className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
                {loading ? '创建订单中...' : '确认支付'}
              </button>
            </div>
          )}

          {/* Order Created */}
          {order && (
            <div className="space-y-4 animate-fade-in">
              {order.status === 'paid' ? (
                <div className="flex flex-col items-center gap-3 py-6">
                  <div className="w-14 h-14 rounded-full bg-success-bg flex items-center justify-center">
                    <CheckCircle className="w-7 h-7 text-success" />
                  </div>
                  <div className="text-base font-semibold text-text-primary">支付成功</div>
                  <div className="text-xs text-text-tertiary">会员已开通，积分已到账</div>
                  <button
                    onClick={onClose}
                    className="mt-2 px-6 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-light transition-all"
                  >
                    完成
                  </button>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between text-xs text-text-secondary">
                    <span>订单号: {order.out_trade_no}</span>
                    <span className={cn(
                      'px-2 py-0.5 rounded-full text-xs font-medium',
                      order.channel === 'mock' ? 'bg-accent-bg text-accent' :
                      order.channel === 'alipay' ? 'bg-blue-500/10 text-blue-500' :
                      'bg-green-500/10 text-green-500'
                    )}>
                      {order.channel === 'mock' ? '模拟支付' : order.channel === 'alipay' ? '支付宝' : '微信支付'}
                    </span>
                  </div>

                  {/* Mock Payment Confirm */}
                  {order.channel === 'mock' && (
                    <div className="space-y-3">
                      <div className="p-4 rounded-xl bg-bg-secondary border border-border text-center">
                        <div className="text-xs text-text-tertiary mb-1">模拟支付金额</div>
                        <div className="text-2xl font-bold text-accent">¥{order.amount}</div>
                      </div>
                      <button
                        onClick={handleMockConfirm}
                        disabled={confirming}
                        className={cn(
                          'w-full py-2.5 rounded-lg text-sm font-medium transition-all',
                          'bg-accent text-white hover:bg-accent-light',
                          'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                          'disabled:opacity-50 flex items-center justify-center gap-1.5 shadow-sm'
                        )}
                      >
                        {confirming ? <Clock className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                        {confirming ? '确认中...' : '模拟支付成功'}
                      </button>
                    </div>
                  )}

                  {/* Alipay / WeChat QR Code */}
                  {(order.channel === 'alipay' || order.channel === 'wechat') && order.qr_code && (
                    <div className="space-y-3">
                      <div className="p-4 rounded-xl bg-bg-secondary border border-border flex flex-col items-center">
                        <div className="text-xs text-text-tertiary mb-2">请使用{order.channel === 'alipay' ? '支付宝' : '微信'}扫码支付</div>
                        {/* 这里可以集成 qrcode.react 生成二维码 */}
                        <div className="w-40 h-40 bg-white rounded-lg flex items-center justify-center">
                          <QrCode className="w-16 h-16 text-text-tertiary" />
                        </div>
                        <div className="text-xs text-text-tertiary mt-2 break-all text-center max-w-[200px]">
                          {order.qr_code}
                        </div>
                      </div>
                      <div className="text-xs text-text-tertiary text-center">
                        支付完成后将自动刷新状态，请勿关闭页面
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-xl bg-danger-bg border border-danger/20 text-danger text-sm">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Plans Tab ───────────────────────────────────────────────────────────────

function PlansTab() {
  const [plans, setPlans] = useState<BillingPlan[]>([])
  const [membership, setMembership] = useState<MembershipInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedPlan, setSelectedPlan] = useState<BillingPlan | null>(null)

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

  const refreshMembership = async () => {
    try {
      const res = await billingApi.getMembership()
      setMembership(res.data?.data || res.data || null)
    } catch { /* silent */ }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40 text-text-tertiary text-sm">加载中...</div>
  }

  // 套餐等级（从低到高，用于判断包含关系）
  const planRank: Record<string, number> = { free: 0, pro: 1, enterprise: 2, lifetime: 3 }
  const userRank = membership?.plan_id ? (planRank[membership.plan_id] ?? 0) : 0

  // Default plans if API returns empty
  const displayPlans: BillingPlan[] = plans.length > 0 ? plans : [
    { id: 'free', name: '免费版', price: 0, credits: 100, features: ['每日 5 次 AI 分析', '基础策略回测', '模拟交易'] },
    { id: 'pro', name: '专业版', price: 99, credits: 5000, features: ['无限 AI 分析', '高级策略回测', '实盘交易', '优先客服'], popular: true },
    { id: 'enterprise', name: '企业版', price: 299, credits: 20000, features: ['全部功能', 'API 接口', '专属客服', '定制策略'] },
    { id: 'lifetime', name: '终身会员', price: 499, credits: 800, features: ['全部功能', 'API 接口', '专属客服', '定制策略', '终身权益'] },
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
              <div className="text-sm font-semibold text-text-primary">当前会员: {membership.level || '免费版'}</div>
              <div className="text-xs text-text-tertiary">
                到期时间: {membership.expires_at ? new Date(membership.expires_at).toLocaleDateString('zh-CN') : '永久'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Plans Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {displayPlans.map((plan) => {
          const currentRank = planRank[plan.id] ?? 0
          const isCurrent = membership?.plan_id === plan.id
          const isIncluded = currentRank < userRank  // 低等级套餐被高等级包含
          const isDisabled = isCurrent || isIncluded || plan.price === 0

          return (
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
                {plan.price > 0 && plan.id !== 'lifetime' && <span className="text-sm text-text-secondary">/月</span>}
                {plan.id === 'lifetime' && <span className="text-sm text-text-secondary">/一次</span>}
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
                onClick={() => {
                  if (!isDisabled && plan.price > 0) {
                    setSelectedPlan(plan)
                  }
                }}
                disabled={isDisabled}
                className={cn(
                  'w-full py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                  'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                  'disabled:opacity-50',
                  isDisabled
                    ? 'bg-bg-secondary text-text-primary'
                    : 'bg-accent text-white hover:bg-accent-light shadow-sm'
                )}
              >
                {isCurrent
                  ? '当前方案'
                  : isIncluded
                    ? '已包含'
                    : plan.price === 0
                      ? '免费版'
                      : '订阅'}
              </button>
            </div>
          )
        })}
      </div>

      {selectedPlan && (
        <PaymentModal
          plan={selectedPlan}
          onClose={() => setSelectedPlan(null)}
          onSuccess={() => {
            setSelectedPlan(null)
            refreshMembership()
          }}
        />
      )}
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
                      log.amount > 0 ? 'bg-rise-bg text-rise' : 'bg-fall-bg text-fall'
                    )}>
                      {log.type}
                    </span>
                  </td>
                  <td className={cn('px-4 py-3 text-right font-medium', log.amount > 0 ? 'text-rise' : 'text-fall')}>
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
      const res = await billingApi.createUsdtPayment(parseFloat(amount).toString())
      setPayment(res.data?.data || res.data || null)
    } catch (err: unknown) {
      setError(getErrorMessage(err, '创建支付失败'))
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

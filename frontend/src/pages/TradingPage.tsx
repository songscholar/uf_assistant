import { useState, useEffect, useCallback } from 'react'
import {
  Wallet,
  ArrowUpDown,
  ListOrdered,
  Package,
  RefreshCw,
  AlertTriangle,
  Settings,
  Zap,
  Shield,
} from 'lucide-react'
import { tradingApi, liveTradingApi, stockApi, getErrorMessage } from '@/lib/api'
import type { Order, Position, Portfolio, LiveOrder, LivePosition, PnLSummary } from '@/types'
import { cn, formatNumber, formatPercent } from '@/lib/utils'

type TradingTab = 'order' | 'positions' | 'orders' | 'trades' | 'credentials'
type TradingMode = 'mock' | 'live'
type MarketFilter = 'crypto' | 'a_share' | 'us_stock'

export default function TradingPage() {
  const [mode, setMode] = useState<TradingMode>('mock')
  const [activeTab, setActiveTab] = useState<TradingTab>('order')
  const [marketFilter, setMarketFilter] = useState<MarketFilter>('crypto')

  // Mock state
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])

  // Live state
  const [livePositions, setLivePositions] = useState<LivePosition[]>([])
  const [liveOrders, setLiveOrders] = useState<LiveOrder[]>([])
  const [liveTrades, setLiveTrades] = useState<any[]>([])
  const [pnl, setPnl] = useState<PnLSummary | null>(null)
  const [balance, setBalance] = useState<Record<string, number>>({})
  const [syncing, setSyncing] = useState(false)

  // Order form
  const [orderSymbol, setOrderSymbol] = useState('')
  const [orderSide, setOrderSide] = useState<'buy' | 'sell'>('buy')
  const [orderPrice, setOrderPrice] = useState('')
  const [orderQuantity, setOrderQuantity] = useState('')
  const [orderLoading, setOrderLoading] = useState(false)
  const [orderMessage, setOrderMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Quote data
  const [quoteData, setQuoteData] = useState<any>(null)
  const [quoteLoading, setQuoteLoading] = useState(false)
  const [maxQuantity, setMaxQuantity] = useState<number | null>(null)

  // Fee estimate
  const [feeEstimate, setFeeEstimate] = useState<any>(null)
  const [feeLoading, setFeeLoading] = useState(false)

  const fetchMockData = useCallback(async () => {
    try {
      const [portfolioRes, positionsRes, ordersRes] = await Promise.all([
        tradingApi.getPortfolio(),
        tradingApi.getPositions(),
        tradingApi.getOrders(),
      ])
      // 防御性解析：后端可能返回嵌套结构 { summary, positions } 或直接数据
      const pfData = portfolioRes.data
      setPortfolio(pfData?.summary || pfData || null)
      const posData = positionsRes.data
      setPositions(Array.isArray(posData) ? posData : (posData?.positions || []))
      const ordData = ordersRes.data
      setOrders(Array.isArray(ordData) ? ordData : (ordData?.orders || []))
    } catch {
      // 首次访问或网络异常时显示默认资产
      setPortfolio({
        total_assets: 5000000,
        available_cash: 5000000,
        position_value: 0,
        total_pnl: 0,
        total_pnl_percent: 0,
      })
      setPositions([])
      setOrders([])
    }
  }, [])

  const fetchLiveData = useCallback(async () => {
    try {
      const [ordersRes, positionsRes, pnlRes, balanceRes, tradesRes] = await Promise.all([
        liveTradingApi.getOrders({ market: marketFilter, limit: 50 }),
        liveTradingApi.getPositions(marketFilter),
        liveTradingApi.getPnL(marketFilter),
        liveTradingApi.getBalance(marketFilter).catch(() => ({ data: null })),
        liveTradingApi.getTrades({ market: marketFilter, limit: 50 }).catch(() => ({ data: null })),
      ])
      const ordData = ordersRes.data
      setLiveOrders(Array.isArray(ordData) ? ordData : (ordData?.orders || []))
      const posData = positionsRes.data
      setLivePositions(Array.isArray(posData) ? posData : (posData?.positions || []))
      setPnl(pnlRes.data || null)
      setBalance(balanceRes.data?.balance || {})
      const tradeData = tradesRes.data
      setLiveTrades(Array.isArray(tradeData) ? tradeData : (tradeData?.trades || []))
    } catch {
      setLiveOrders([])
      setLivePositions([])
      setLiveTrades([])
    }
  }, [marketFilter])

  useEffect(() => {
    if (mode === 'mock') fetchMockData()
    else fetchLiveData()
  }, [mode, fetchMockData, fetchLiveData])

  // 获取行情
  const fetchQuote = useCallback(async (symbol: string) => {
    if (!symbol || mode !== 'mock') return
    setQuoteLoading(true)
    try {
      const res = await stockApi.getRealtime(symbol)
      setQuoteData(res.data)
    } catch {
      setQuoteData(null)
    } finally {
      setQuoteLoading(false)
    }
  }, [mode])

  // 代码变化时延迟获取行情
  useEffect(() => {
    const timer = setTimeout(() => {
      if (orderSymbol) fetchQuote(orderSymbol)
    }, 500)
    return () => clearTimeout(timer)
  }, [orderSymbol, fetchQuote])

  // 价格/方向变化时计算最大可买/卖数量
  useEffect(() => {
    if (orderSide === 'buy') {
      // 优先用输入的价格，没有则用行情价
      const rawPrice = orderPrice || (quoteData?.price ? String(quoteData.price) : '')
      if (!rawPrice) {
        setMaxQuantity(null)
        return
      }
      const price = parseFloat(rawPrice)
      if (price <= 0 || isNaN(price)) {
        setMaxQuantity(null)
        return
      }
      const cash = portfolio?.available_cash || 0
      const qty = Math.floor(cash / price / 100) * 100
      setMaxQuantity(Math.max(0, qty))
    } else {
      // 卖出不需要价格，只看持仓
      if (!orderSymbol) {
        setMaxQuantity(null)
        return
      }
      const pos = positions.find((p: any) => p.symbol === orderSymbol)
      if (pos) {
        const qty = Math.floor(pos.quantity / 100) * 100
        setMaxQuantity(Math.max(0, qty))
      } else {
        setMaxQuantity(0)
      }
    }
  }, [orderPrice, orderSide, orderSymbol, portfolio, positions, quoteData])

  // 费用预估
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!orderSymbol || !orderQuantity) {
        setFeeEstimate(null)
        return
      }
      const qty = parseFloat(orderQuantity)
      if (isNaN(qty) || qty <= 0) {
        setFeeEstimate(null)
        return
      }
      let price: number
      if (orderPrice) {
        price = parseFloat(orderPrice)
        if (isNaN(price) || price <= 0) {
          setFeeEstimate(null)
          return
        }
      } else if (quoteData?.price) {
        price = quoteData.price
      } else {
        setFeeEstimate(null)
        return
      }
      setFeeLoading(true)
      tradingApi.estimateFee({
        symbol: orderSymbol,
        side: orderSide,
        quantity: qty,
        price: price,
      }).then((res) => {
        setFeeEstimate(res.data)
      }).catch(() => {
        setFeeEstimate(null)
      }).finally(() => {
        setFeeLoading(false)
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [orderSymbol, orderSide, orderPrice, orderQuantity, quoteData])

  const handleSubmitOrder = async () => {
    if (!orderSymbol || !orderQuantity) {
      setOrderMessage({ type: 'error', text: '请填写股票代码和数量' })
      return
    }
    // 限价校验
    if (orderPrice && quoteData) {
      const price = parseFloat(orderPrice)
      if (quoteData.limit_up != null && price > quoteData.limit_up) {
        setOrderMessage({ type: 'error', text: `委托价不能高于涨停价 ${quoteData.limit_up.toFixed(2)}` })
        return
      }
      if (quoteData.limit_down != null && price < quoteData.limit_down) {
        setOrderMessage({ type: 'error', text: `委托价不能低于跌停价 ${quoteData.limit_down.toFixed(2)}` })
        return
      }
    }
    setOrderLoading(true)
    setOrderMessage(null)
    try {
      if (mode === 'mock') {
        await tradingApi.submitOrder({
          symbol: orderSymbol,
          side: orderSide,
          quantity: parseFloat(orderQuantity),
          price: orderPrice ? parseFloat(orderPrice) : undefined,
          order_type: orderPrice ? 'limit' : 'market',
        })
      } else {
        await liveTradingApi.submitOrder({
          market: marketFilter,
          symbol: orderSymbol,
          side: orderSide,
          quantity: parseFloat(orderQuantity),
          price: orderPrice ? parseFloat(orderPrice) : undefined,
          order_type: orderPrice ? 'limit' : 'market',
        })
      }
      setOrderSymbol('')
      setOrderPrice('')
      setOrderQuantity('')
      setOrderMessage({ type: 'success', text: '下单成功' })
      // Refresh data
      if (mode === 'mock') fetchMockData()
      else fetchLiveData()
    } catch (err) {
      setOrderMessage({ type: 'error', text: getErrorMessage(err, '下单失败') })
    } finally {
      setOrderLoading(false)
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      await liveTradingApi.syncPositions(marketFilter)
      await fetchLiveData()
    } catch {
      // silent
    } finally {
      setSyncing(false)
    }
  }

  const handleCancelOrder = async (orderId: string) => {
    try {
      if (mode === 'mock') {
        await tradingApi.cancelOrder(orderId)
        fetchMockData()
      } else {
        await liveTradingApi.cancelOrder(orderId, marketFilter)
        fetchLiveData()
      }
    } catch {
      // silent
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Mode Toggle + Market Filter */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="flex bg-bg-secondary rounded-lg p-0.5">
            {[
              { key: 'mock' as const, label: '模拟交易', icon: Shield },
              { key: 'live' as const, label: '实盘交易', icon: Zap },
            ].map((m) => (
              <button
                key={m.key}
                onClick={() => setMode(m.key)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200',
                  mode === m.key
                    ? 'bg-bg-card text-accent shadow-sm'
                    : 'text-text-secondary hover:text-text-primary'
                )}
              >
                <m.icon className="w-3.5 h-3.5" />
                {m.label}
              </button>
            ))}
          </div>

          {mode === 'live' && (
            <div className="flex bg-bg-secondary rounded-lg p-0.5">
              {([
                { key: 'crypto' as const, label: '加密' },
                { key: 'a_share' as const, label: 'A股' },
                { key: 'us_stock' as const, label: '美股' },
              ]).map((m) => (
                <button
                  key={m.key}
                  onClick={() => setMarketFilter(m.key)}
                  className={cn(
                    'px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200',
                    marketFilter === m.key
                      ? 'bg-bg-card text-accent shadow-sm'
                      : 'text-text-secondary hover:text-text-primary'
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {mode === 'live' && (
          <button
            onClick={handleSync}
            disabled={syncing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                       bg-bg-hover text-text-secondary hover:bg-bg-active hover:text-text-primary
                       transition-smooth disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', syncing && 'animate-spin')} />
            同步持仓
          </button>
        )}
      </div>

      {mode === 'live' && (
        <div className="mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-600 text-sm flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>实盘交易涉及真实资金，请谨慎操作。请先在「凭证管理」中配置交易所 API Key。</div>
        </div>
      )}

      {/* Summary Cards */}
      {mode === 'mock' && portfolio && (
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          {[
            { label: '总资产', value: `¥${formatNumber(portfolio.total_assets)}` },
            { label: '可用资金', value: `¥${formatNumber(portfolio.available_cash)}` },
            { label: '持仓市值', value: `¥${formatNumber(portfolio.position_value)}` },
            { label: '累计收益', value: `${portfolio.total_pnl >= 0 ? '+' : ''}¥${formatNumber(portfolio.total_pnl)} (${portfolio.total_pnl >= 0 ? '+' : ''}${formatPercent(portfolio.total_pnl_percent)})`, color: portfolio.total_pnl >= 0 ? 'text-rise' : 'text-fall' },
          ].map((item) => (
            <div key={item.label} className="bg-bg-card border border-border rounded-xl p-4 card-hover cursor-pointer">
              <div className="text-xs text-text-tertiary mb-1">{item.label}</div>
              <div className={cn('text-xl font-bold', item.color || 'text-text-primary')}>{item.value}</div>
            </div>
          ))}
        </section>
      )}

      {mode === 'live' && (
        <section className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">已实现盈亏</div>
            <div className={cn('text-xl font-bold', (pnl?.total_realized ?? 0) >= 0 ? 'text-rise' : 'text-fall')}>
              {pnl?.total_realized?.toFixed(2) ?? '0.00'}
            </div>
          </div>
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">未实现盈亏</div>
            <div className={cn('text-xl font-bold', (pnl?.total_unrealized ?? 0) >= 0 ? 'text-rise' : 'text-fall')}>
              {pnl?.total_unrealized?.toFixed(2) ?? '0.00'}
            </div>
          </div>
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">总盈亏</div>
            <div className={cn('text-xl font-bold', (pnl?.total_pnl ?? 0) >= 0 ? 'text-rise' : 'text-fall')}>
              {pnl?.total_pnl?.toFixed(2) ?? '0.00'}
            </div>
          </div>
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">总手续费</div>
            <div className="text-xl font-bold text-text-secondary">{pnl?.total_fee?.toFixed(2) ?? '0.00'}</div>
          </div>
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">可用余额</div>
            <div className="text-xl font-bold text-text-primary">
              {Object.entries(balance).map(([k, v]) => `${v.toFixed(2)} ${k}`).join(', ') || '--'}
            </div>
          </div>
        </section>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-4 border-b border-border">
        {[
          { key: 'order' as const, label: '下单', icon: ArrowUpDown },
          { key: 'positions' as const, label: '持仓', icon: Package },
          { key: 'orders' as const, label: '订单', icon: ListOrdered },
          ...(mode === 'live' ? [
            { key: 'trades' as const, label: '成交', icon: ArrowUpDown },
            { key: 'credentials' as const, label: '凭证管理', icon: Settings },
          ] : []),
        ].map((tab) => (
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

      {/* Order Form */}
      {activeTab === 'order' && (
        <div className="flex gap-4">
          {/* 左侧：下单表单 */}
          <div className="bg-bg-card border border-border rounded-xl p-4 w-full max-w-md card-hover">
            <div className="space-y-4">
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">
                  {mode === 'live' ? '交易对 / 股票代码' : '股票代码'}
                </label>
                <input
                  type="text"
                  value={orderSymbol}
                  onChange={(e) => setOrderSymbol(e.target.value)}
                  placeholder={mode === 'live' && marketFilter === 'crypto' ? 'BTC/USDT' : '600519'}
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                />
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">买卖方向</label>
                <div className="flex gap-2">
                  {(['buy', 'sell'] as const).map((side) => (
                    <button
                      key={side}
                      onClick={() => setOrderSide(side)}
                      className={cn(
                        'flex-1 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                        orderSide === side
                          ? side === 'buy' ? 'bg-[rgba(74,222,128,0.15)] text-[#4ade80]' : 'bg-[rgba(248,113,113,0.15)] text-[#f87171]'
                          : 'bg-bg-secondary text-text-secondary hover:bg-bg-hover'
                      )}
                    >
                      {side === 'buy' ? '买入' : '卖出'}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">价格</label>
                <input
                  type="number"
                  step="0.01"
                  value={orderPrice}
                  onChange={(e) => {
                    const v = e.target.value
                    if (v === '' || /^\d+(\.\d{0,2})?$/.test(v)) {
                      setOrderPrice(v)
                    }
                  }}
                  placeholder="留空为市价"
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                />
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">数量</label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={orderQuantity}
                  onChange={(e) => {
                    const v = e.target.value
                    if (v === '' || /^\d+$/.test(v)) {
                      setOrderQuantity(v)
                    }
                  }}
                  placeholder={mode === 'live' && marketFilter === 'crypto' ? '1' : '100'}
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                />
                {maxQuantity !== null && maxQuantity >= 0 && (
                  <div className="text-xs text-text-tertiary mt-1">
                    {orderSide === 'buy'
                      ? `当前可买数量：${maxQuantity} 股`
                      : `当前可卖数量：${maxQuantity} 股`}
                  </div>
                )}
              </div>
              {/* 费用预估 */}
              {mode === 'mock' && feeEstimate && (
                <div className="bg-bg-secondary rounded-lg p-3 text-xs space-y-1">
                  <div className="text-text-secondary font-medium mb-1">费用预估</div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">成交金额</span>
                    <span className="text-text-primary">¥{formatNumber(feeEstimate.amount)}</span>
                  </div>
                  <div className="group relative flex justify-between cursor-help">
                    <span className="text-text-tertiary underline decoration-dotted decoration-text-tertiary/50">佣金</span>
                    <span className="text-text-primary">¥{formatNumber(feeEstimate.fees?.commission)}</span>
                    <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10 w-56 bg-bg-card border border-border rounded-lg p-2 shadow-lg text-[11px] text-text-secondary leading-relaxed">
                      <div className="font-medium text-text-primary mb-0.5">佣金</div>
                      <div>公式：成交金额 × 0.03%</div>
                      <div>说明：最低 5 元，买入卖出均收取</div>
                    </div>
                  </div>
                  {feeEstimate.fees?.stamp_tax > 0 && (
                    <div className="group relative flex justify-between cursor-help">
                      <span className="text-text-tertiary underline decoration-dotted decoration-text-tertiary/50">印花税</span>
                      <span className="text-text-primary">¥{formatNumber(feeEstimate.fees?.stamp_tax)}</span>
                      <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10 w-56 bg-bg-card border border-border rounded-lg p-2 shadow-lg text-[11px] text-text-secondary leading-relaxed">
                        <div className="font-medium text-text-primary mb-0.5">印花税</div>
                        <div>公式：成交金额 × 0.1%</div>
                        <div>说明：仅卖出时收取，买入不收</div>
                      </div>
                    </div>
                  )}
                  <div className="group relative flex justify-between cursor-help">
                    <span className="text-text-tertiary underline decoration-dotted decoration-text-tertiary/50">过户费</span>
                    <span className="text-text-primary">¥{formatNumber(feeEstimate.fees?.transfer_fee)}</span>
                    <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10 w-56 bg-bg-card border border-border rounded-lg p-2 shadow-lg text-[11px] text-text-secondary leading-relaxed">
                      <div className="font-medium text-text-primary mb-0.5">过户费</div>
                      <div>公式：成交金额 × 0.002%</div>
                      <div>说明：买入卖出均收取</div>
                    </div>
                  </div>
                  <div className="group relative flex justify-between cursor-help">
                    <span className="text-text-tertiary underline decoration-dotted decoration-text-tertiary/50">交易所费用</span>
                    <span className="text-text-primary">¥{formatNumber(feeEstimate.fees?.exchange_fee)}</span>
                    <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10 w-56 bg-bg-card border border-border rounded-lg p-2 shadow-lg text-[11px] text-text-secondary leading-relaxed">
                      <div className="font-medium text-text-primary mb-0.5">交易所费用</div>
                      <div>公式：成交金额 × 0.00487%</div>
                      <div>说明：含证管费 + 经手费，买入卖出均收取</div>
                    </div>
                  </div>
                  <div className="flex justify-between border-t border-border-light pt-1 mt-1">
                    <span className="text-text-secondary font-medium">总费用</span>
                    <span className="text-text-primary font-medium">¥{formatNumber(feeEstimate.fees?.total)}</span>
                  </div>
                  <div className="flex justify-between pt-1">
                    <span className="text-text-secondary font-medium">总金额</span>
                    <span className={cn(
                      'font-medium',
                      orderSide === 'buy' ? 'text-[#4ade80]' : 'text-[#f87171]'
                    )}>
                      ¥{formatNumber((feeEstimate.amount || 0) + (feeEstimate.fees?.total || 0))}
                    </span>
                  </div>
                </div>
              )}
              {orderMessage && (
                <div className={cn(
                  'text-xs rounded-lg px-3 py-2',
                  orderMessage.type === 'success'
                    ? 'text-[#4ade80] bg-[rgba(74,222,128,0.1)]'
                    : 'text-[#f87171] bg-[rgba(248,113,113,0.1)]'
                )}>
                  {orderMessage.text}
                </div>
              )}
              <button
                onClick={handleSubmitOrder}
                disabled={orderLoading}
                className={cn(
                  'w-full py-2.5 rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50',
                  orderSide === 'buy'
                    ? 'bg-[rgba(74,222,128,0.15)] text-[#4ade80] hover:bg-[rgba(74,222,128,0.25)] hover:-translate-y-[1px] hover:shadow-md active:translate-y-0'
                    : 'bg-[rgba(248,113,113,0.15)] text-[#f87171] hover:bg-[rgba(248,113,113,0.25)] hover:-translate-y-[1px] hover:shadow-md active:translate-y-0'
                )}
              >
                {orderLoading ? '提交中...' : `确认${orderSide === 'buy' ? '买入' : '卖出'}`}
              </button>
            </div>
          </div>

          {/* 右侧：行情展示 */}
          {mode === 'mock' && (
            <div className="flex-1 bg-bg-card border border-border rounded-xl p-4 card-hover min-w-[280px]">
              <div className="text-sm font-medium text-text-primary mb-3">行情信息</div>
              {quoteLoading ? (
                <div className="text-xs text-text-tertiary">加载中...</div>
              ) : quoteData ? (
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">名称</span>
                    <span className="text-text-primary font-medium">{quoteData.name || '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">现价</span>
                    <span className={cn(
                      'font-medium',
                      (quoteData.change_pct || 0) >= 0 ? 'text-[#4ade80]' : 'text-[#f87171]'
                    )}>
                      {quoteData.price?.toFixed(2) ?? '--'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">涨跌幅</span>
                    <span className={cn(
                      'font-medium',
                      (quoteData.change_pct || 0) >= 0 ? 'text-[#4ade80]' : 'text-[#f87171]'
                    )}>
                      {quoteData.change_pct != null ? `${quoteData.change_pct >= 0 ? '+' : ''}${quoteData.change_pct.toFixed(2)}%` : '--'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">涨跌额</span>
                    <span className={cn(
                      'font-medium',
                      (quoteData.change_pct || 0) >= 0 ? 'text-[#4ade80]' : 'text-[#f87171]'
                    )}>
                      {quoteData.price != null && quoteData.prev_close != null
                        ? `${(quoteData.price - quoteData.prev_close) >= 0 ? '+' : ''}${(quoteData.price - quoteData.prev_close).toFixed(2)}`
                        : '--'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">今开</span>
                    <span className="text-text-primary">{quoteData.open?.toFixed(2) ?? '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">最高</span>
                    <span className="text-text-primary">{quoteData.high?.toFixed(2) ?? '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">最低</span>
                    <span className="text-text-primary">{quoteData.low?.toFixed(2) ?? '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">涨停价</span>
                    <span className="text-[#f87171]">{quoteData.limit_up?.toFixed(2) ?? '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">跌停价</span>
                    <span className="text-[#4ade80]">{quoteData.limit_down?.toFixed(2) ?? '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">成交量</span>
                    <span className="text-text-primary">{quoteData.volume != null ? formatNumber(quoteData.volume) : '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">成交额</span>
                    <span className="text-text-primary">{quoteData.amount != null ? formatNumber(quoteData.amount) : '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">市盈率(TTM)</span>
                    <span className="text-text-primary">{quoteData.pe_ttm?.toFixed(2) ?? '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">总市值</span>
                    <span className="text-text-primary">{quoteData.market_cap != null ? `${(quoteData.market_cap / 1e8).toFixed(2)}亿` : '--'}</span>
                  </div>
                </div>
              ) : orderSymbol ? (
                <div className="text-xs text-text-tertiary">未找到该股票行情</div>
              ) : (
                <div className="text-xs text-text-tertiary">请输入股票代码查看行情</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Positions */}
      {activeTab === 'positions' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                {mode === 'live'
                  ? (
                      <>
                        <th className="text-left px-4 py-2 font-medium">市场</th>
                        <th className="text-left px-4 py-2 font-medium">代码</th>
                        <th className="text-left px-4 py-2 font-medium">数量</th>
                        <th className="text-left px-4 py-2 font-medium">成本</th>
                        <th className="text-left px-4 py-2 font-medium">现价</th>
                        <th className="text-left px-4 py-2 font-medium">未实现盈亏</th>
                      </>
                    )
                  : (
                      <>
                        <th className="text-left px-4 py-2 font-medium">代码</th>
                        <th className="text-left px-4 py-2 font-medium">名称</th>
                        <th className="text-left px-4 py-2 font-medium">数量</th>
                        <th className="text-left px-4 py-2 font-medium">成本</th>
                        <th className="text-left px-4 py-2 font-medium">现价</th>
                        <th className="text-left px-4 py-2 font-medium">市值</th>
                        <th className="text-left px-4 py-2 font-medium">盈亏</th>
                        <th className="text-left px-4 py-2 font-medium">收益率</th>
                        <th className="text-left px-4 py-2 font-medium">费用</th>
                      </>
                    )
                }
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {mode === 'live'
                ? livePositions.map((pos) => (
                    <tr key={`${pos.market}-${pos.symbol}`} className="hover:bg-bg-hover transition-colors duration-150 cursor-pointer">
                      <td className="px-4 py-3 text-text-secondary">{pos.market}</td>
                      <td className="px-4 py-3 text-text-primary font-medium">{pos.symbol}</td>
                      <td className="px-4 py-3 text-left text-text-primary">{pos.quantity}</td>
                      <td className="px-4 py-3 text-left text-text-secondary">{pos.avg_cost?.toFixed(2)}</td>
                      <td className="px-4 py-3 text-left text-text-primary">{pos.current_price?.toFixed(2) ?? '--'}</td>
                      <td className={cn('px-4 py-3 text-left font-medium', (pos.unrealized_pnl ?? 0) >= 0 ? 'text-rise' : 'text-fall')}>
                        {(pos.unrealized_pnl ?? 0) >= 0 ? '+' : ''}{pos.unrealized_pnl?.toFixed(2) ?? '--'}
                      </td>
                    </tr>
                  ))
                : positions.map((pos) => (
                    <tr key={pos.symbol} className="hover:bg-bg-hover transition-colors duration-150 cursor-pointer">
                      <td className="px-4 py-3 text-text-primary font-medium">{pos.symbol}</td>
                      <td className="px-4 py-3 text-text-secondary">{pos.name}</td>
                      <td className="px-4 py-3 text-left text-text-primary">{pos.quantity}</td>
                      <td className="px-4 py-3 text-left text-text-secondary">{formatNumber(pos.avg_cost)}</td>
                      <td className="px-4 py-3 text-left text-text-primary">{formatNumber(pos.current_price)}</td>
                      <td className="px-4 py-3 text-left text-text-primary">{formatNumber(pos.market_value)}</td>
                      <td className={cn('px-4 py-3 text-left font-medium', pos.pnl >= 0 ? 'text-rise' : 'text-fall')}>
                        {pos.pnl >= 0 ? '+' : ''}¥{formatNumber(Math.abs(pos.pnl))}
                      </td>
                      <td className={cn('px-4 py-3 text-left font-medium', pos.pnl >= 0 ? 'text-rise' : 'text-fall')}>
                        {pos.pnl >= 0 ? '+' : ''}{formatPercent(pos.pnl_percent)}
                      </td>
                      <td className="px-4 py-3 text-left text-text-secondary">
                        {pos.total_fee != null ? formatNumber(pos.total_fee) : '--'}
                      </td>
                    </tr>
                  ))
              }
              {(mode === 'live' ? livePositions : positions).length === 0 && (
                <tr>
                  <td colSpan={mode === 'live' ? 6 : 9} className="px-4 py-8 text-center text-text-tertiary text-sm">暂无持仓</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Orders */}
      {activeTab === 'orders' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                {['时间', mode === 'live' ? '市场' : null, '代码', '方向', '类型', '价格', '数量', '费用', '状态', '操作']
                  .filter(Boolean)
                  .map((h) => (
                    <th key={h as string} className="text-left px-4 py-2 font-medium">{h}</th>
                  ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {(mode === 'live' ? liveOrders : orders).map((order) => {
                const isLive = mode === 'live'
                const o = order as LiveOrder & Order
                return (
                  <tr key={o.id || o.order_id} className="hover:bg-bg-hover transition-colors duration-150">
                    <td className="px-4 py-3 text-text-secondary text-xs">
                      {new Date(o.created_at).toLocaleString('zh-CN')}
                    </td>
                    {isLive && <td className="px-4 py-3 text-text-secondary">{o.market}</td>}
                    <td className="px-4 py-3 text-text-primary font-medium">{o.symbol}</td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        'px-2 py-0.5 rounded text-xs font-medium',
                        o.side === 'buy' ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                      )}>
                        {o.side === 'buy' ? '买入' : '卖出'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{o.order_type}</td>
                    <td className="px-4 py-3 text-right text-text-primary">
                      {(o as any).filled_price != null
                        ? formatNumber((o as any).filled_price)
                        : o.price != null
                          ? formatNumber(o.price)
                          : '市价'}
                    </td>
                    <td className="px-4 py-3 text-right text-text-primary">{o.quantity}</td>
                    <td className="px-4 py-3 text-right text-text-secondary">
                      {(o as any).total_fee != null ? formatNumber((o as any).total_fee) : '--'}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={o.status} />
                    </td>
                    <td className="px-4 py-3">
                      {o.status === 'pending' || o.status === 'submitted' ? (
                        <button
                          onClick={() => handleCancelOrder(o.id || o.order_id)}
                          className="text-xs text-danger hover:underline"
                        >
                          取消
                        </button>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
              {(mode === 'live' ? liveOrders : orders).length === 0 && (
                <tr>
                  <td colSpan={mode === 'live' ? 10 : 9} className="px-4 py-8 text-center text-text-tertiary text-sm">暂无订单</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Trades (live mode only) */}
      {activeTab === 'trades' && mode === 'live' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                {['时间', '市场', '代码', '方向', '成交价格', '数量', '手续费'].map((h) => (
                  <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {liveTrades.map((trade, i) => (
                <tr key={i} className="hover:bg-bg-hover transition-colors duration-150">
                  <td className="px-4 py-3 text-text-secondary text-xs">
                    {trade.timestamp ? new Date(trade.timestamp).toLocaleString('zh-CN') : '--'}
                  </td>
                  <td className="px-4 py-3 text-text-secondary">{trade.market || marketFilter}</td>
                  <td className="px-4 py-3 text-text-primary font-medium">{trade.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      trade.side === 'buy' ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                    )}>
                      {trade.side === 'buy' ? '买入' : '卖出'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-text-primary">{trade.price?.toFixed ? trade.price.toFixed(4) : trade.price}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{trade.quantity}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{trade.fee?.toFixed ? trade.fee.toFixed(4) : trade.fee || '--'}</td>
                </tr>
              ))}
              {liveTrades.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-text-tertiary text-sm">暂无成交记录</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Credentials (live mode only) */}
      {activeTab === 'credentials' && mode === 'live' && (
        <CredentialsPanel />
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    pending: { label: '待提交', className: 'bg-gray-500/10 text-gray-500' },
    submitted: { label: '已提交', className: 'bg-blue-500/10 text-blue-500' },
    filled: { label: '已成交', className: 'bg-success-bg text-success' },
    partial_filled: { label: '部分成交', className: 'bg-yellow-500/10 text-yellow-500' },
    cancelled: { label: '已取消', className: 'bg-gray-500/10 text-gray-500' },
    rejected: { label: '已拒绝', className: 'bg-danger-bg text-danger' },
  }
  const c = config[status] || { label: status, className: 'bg-gray-500/10 text-gray-500' }
  return <span className={cn('px-2 py-0.5 rounded text-xs font-medium', c.className)}>{c.label}</span>
}

function CredentialsPanel() {
  const [credentials, setCredentials] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ market: 'crypto', name: '', api_key: '', api_secret: '', exchange: 'gate' })
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({ name: '', api_key: '', api_secret: '', is_active: true })
  const [updating, setUpdating] = useState(false)

  const fetchCredentials = async () => {
    try {
      const { credentialsApi } = await import('@/lib/api')
      const res = await credentialsApi.list()
      setCredentials(res.data?.credentials || [])
    } catch {
      // silent
    }
  }

  useEffect(() => { fetchCredentials() }, [])

  const handleAdd = async () => {
    try {
      const { credentialsApi } = await import('@/lib/api')
      await credentialsApi.add({
        market: form.market,
        name: form.name,
        api_key: form.api_key,
        api_secret: form.api_secret,
        extra_config: form.market === 'crypto' ? { exchange: form.exchange } : undefined,
      })
      setShowAdd(false)
      setForm({ market: 'crypto', name: '', api_key: '', api_secret: '', exchange: 'gate' })
      fetchCredentials()
    } catch {
      // silent
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const { credentialsApi } = await import('@/lib/api')
      const res = await credentialsApi.test({
        market: form.market,
        api_key: form.api_key,
        api_secret: form.api_secret,
        extra_config: form.market === 'crypto' ? { exchange: form.exchange } : undefined,
      })
      setTestResult(res.data)
    } catch (err: any) {
      setTestResult({ success: false, message: getErrorMessage(err, '测试失败') })
    } finally {
      setTesting(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      const { credentialsApi } = await import('@/lib/api')
      await credentialsApi.delete(id)
      fetchCredentials()
    } catch {
      // silent
    }
  }

  const startEdit = (cred: any) => {
    setEditingId(cred.id)
    setEditForm({
      name: cred.name || '',
      api_key: '',
      api_secret: '',
      is_active: cred.is_active !== false,
    })
  }

  const handleUpdate = async (id: string) => {
    setUpdating(true)
    try {
      const { credentialsApi } = await import('@/lib/api')
      const payload: Record<string, unknown> = { name: editForm.name, is_active: editForm.is_active }
      if (editForm.api_key) payload.api_key = editForm.api_key
      if (editForm.api_secret) payload.api_secret = editForm.api_secret
      await credentialsApi.update(id, payload)
      setEditingId(null)
      fetchCredentials()
    } catch {
      // silent
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-primary">已保存的凭证</h3>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-accent text-white hover:opacity-90 transition-all"
        >
          {showAdd ? '取消' : '添加凭证'}
        </button>
      </div>

      {showAdd && (
        <div className="bg-bg-card border border-border rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">市场</label>
              <select
                value={form.market}
                onChange={(e) => setForm({ ...form, market: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm"
              >
                <option value="crypto">加密货币</option>
                <option value="a_share">A股</option>
                <option value="us_stock">美股</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">名称</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="如 Gate.io 主账户"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm"
              />
            </div>
          </div>
          {form.market === 'crypto' && (
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">交易所</label>
              <select
                value={form.exchange}
                onChange={(e) => setForm({ ...form, exchange: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm"
              >
                <option value="gate">Gate.io</option>
                <option value="binance">Binance</option>
                <option value="okx">OKX</option>
                <option value="bybit">Bybit</option>
              </select>
            </div>
          )}
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">API Key</label>
            <input
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder="API Key"
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">API Secret</label>
            <input
              type="password"
              value={form.api_secret}
              onChange={(e) => setForm({ ...form, api_secret: e.target.value })}
              placeholder="API Secret"
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm font-mono"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleTest}
              disabled={testing || !form.api_key || !form.api_secret}
              className="px-4 py-2 rounded-lg text-xs font-medium bg-bg-hover text-text-secondary hover:bg-bg-active transition-all disabled:opacity-50"
            >
              {testing ? '测试中...' : '测试连接'}
            </button>
            <button
              onClick={handleAdd}
              disabled={!form.name || !form.api_key || !form.api_secret}
              className="px-4 py-2 rounded-lg text-xs font-medium bg-accent text-white hover:opacity-90 transition-all disabled:opacity-50"
            >
              保存
            </button>
          </div>
          {testResult && (
            <div className={cn(
              'p-3 rounded-lg text-sm',
              testResult.success ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
            )}>
              {testResult.message}
            </div>
          )}
        </div>
      )}

      <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg-secondary text-text-secondary text-xs">
              {['市场', '名称', 'API Key', '状态', '操作'].map((h) => (
                <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">
            {credentials.map((cred) => (
              <>
                <tr key={cred.id} className="hover:bg-bg-hover transition-colors duration-150">
                  <td className="px-4 py-3 text-text-primary">{cred.market}</td>
                  <td className="px-4 py-3 text-text-primary">{cred.name}</td>
                  <td className="px-4 py-3 text-text-secondary font-mono text-xs">{cred.api_key_masked}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      cred.is_active ? 'bg-success-bg text-success' : 'bg-gray-500/10 text-gray-500'
                    )}>
                      {cred.is_active ? '启用' : '禁用'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => startEdit(cred)}
                        className="text-xs text-accent hover:underline"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => handleDelete(cred.id)}
                        className="text-xs text-danger hover:underline"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
                {editingId === cred.id && (
                  <tr>
                    <td colSpan={5} className="px-4 py-3 bg-bg-secondary/50">
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                          <label className="text-xs text-text-tertiary mb-1 block">名称</label>
                          <input
                            value={editForm.name}
                            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                            className="w-full px-3 py-1.5 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-text-tertiary mb-1 block">API Key (留空则不修改)</label>
                          <input
                            value={editForm.api_key}
                            onChange={(e) => setEditForm({ ...editForm, api_key: e.target.value })}
                            placeholder="新 API Key"
                            className="w-full px-3 py-1.5 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm font-mono"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-text-tertiary mb-1 block">API Secret (留空则不修改)</label>
                          <input
                            type="password"
                            value={editForm.api_secret}
                            onChange={(e) => setEditForm({ ...editForm, api_secret: e.target.value })}
                            placeholder="新 API Secret"
                            className="w-full px-3 py-1.5 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm font-mono"
                          />
                        </div>
                      </div>
                      <div className="flex items-center gap-3 mt-3">
                        <label className="flex items-center gap-1.5 text-sm text-text-secondary cursor-pointer">
                          <input
                            type="checkbox"
                            checked={editForm.is_active}
                            onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                            className="accent-accent"
                          />
                          启用
                        </label>
                        <button
                          onClick={() => handleUpdate(cred.id)}
                          disabled={updating}
                          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-accent text-white hover:opacity-90 transition-all disabled:opacity-50"
                        >
                          {updating ? '保存中...' : '保存'}
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-hover text-text-secondary hover:bg-bg-active transition-all"
                        >
                          取消
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
            {credentials.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text-tertiary text-sm">
                  暂无凭证，请添加交易所 API Key
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

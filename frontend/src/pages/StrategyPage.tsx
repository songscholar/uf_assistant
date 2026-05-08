import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Brain,
  Play,
  Search,
  FlaskConical,
  BarChart3,
  Activity,
  Package,
  ListOrdered,
  Square,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Zap,
  AlertCircle,
  Sparkles,
  Filter,
  Wand2,
} from 'lucide-react'
import { strategyApi, strategyEngineApi } from '@/lib/api'
import type {
  StrategyInfo,
  StrategySignal,
  StrategyListItem,
  BacktestResult,
  Indicator,
  StrategyPositionItem,
  StrategyTrade,
  RuntimeMetrics,
  EquityPoint,
} from '@/types'
import { cn, formatNumber, formatPercent } from '@/lib/utils'

type StrategyTab = 'library' | 'backtest' | 'indicators' | 'running' | 'positions'

const TABS = [
  { key: 'library' as const, label: '策略库', icon: Brain },
  { key: 'backtest' as const, label: '回测', icon: FlaskConical },
  { key: 'indicators' as const, label: '指标', icon: BarChart3 },
  { key: 'running' as const, label: '运行中', icon: Activity },
  { key: 'positions' as const, label: '持仓/交易', icon: Package },
]

// ── Strategy Card ───────────────────────────────────────────────────────────

function StrategyCard({ strategy, onEvaluate }: { strategy: StrategyInfo; onEvaluate: () => void }) {
  return (
    <div className={cn('bg-bg-card border border-border rounded-xl p-4 card-hover cursor-pointer relative overflow-hidden')}>
      <div className="flex items-start justify-between mb-2">
        <div className="w-10 h-10 rounded-lg bg-accent-bg flex items-center justify-center">
          <Brain className="w-5 h-5 text-accent" />
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onEvaluate() }}
          className={cn(
            'px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200',
            'bg-accent text-white hover:bg-accent-light',
            'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
            'flex items-center gap-1 shadow-sm hover:shadow-md'
          )}
        >
          <Play className="w-3.5 h-3.5" />
          运行
        </button>
      </div>
      <h3 className="font-semibold text-text-primary mb-1">{strategy.name}</h3>
      <p className="text-sm text-text-secondary">{strategy.description}</p>
    </div>
  )
}

// ── Equity Chart ────────────────────────────────────────────────────────────

function EquityChart({ data }: { data: EquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<unknown>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    let disposed = false

    import('lightweight-charts').then(({ createChart, ColorType, AreaSeries }) => {
      if (disposed || !containerRef.current) return

      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 260,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: getComputedStyle(document.documentElement).getPropertyValue('--color-text-secondary').trim() || '#94a3b8',
        },
        grid: {
          vertLines: { color: 'rgba(148,163,184,0.08)' },
          horzLines: { color: 'rgba(148,163,184,0.08)' },
        },
        rightPriceScale: { borderVisible: false },
        timeScale: { borderVisible: false, timeVisible: false },
      })

      chartRef.current = chart

      const series = chart.addSeries(AreaSeries, {
        lineColor: getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim() || '#60a5fa',
        topColor: 'rgba(96,165,250,0.25)',
        bottomColor: 'rgba(96,165,250,0.02)',
        lineWidth: 2,
      })

      series.setData(
        data.map((p) => ({
          time: p.timestamp.split('T')[0] || p.timestamp,
          value: p.equity,
        }))
      )

      chart.timeScale().fitContent()
    })

    return () => {
      disposed = true
      if (chartRef.current) {
        (chartRef.current as { remove: () => void }).remove()
        chartRef.current = null
      }
    }
  }, [data])

  return <div ref={containerRef} className="w-full" />
}

// ── Backtest Tab ────────────────────────────────────────────────────────────

function BacktestTab() {
  const [code, setCode] = useState(`# 策略代码\n# 使用 @param 声明可调参数\n\n# @param fast_period int 5 快线周期\n# @param slow_period int 20 慢线周期\n\ndef on_bar(ctx):\n    fast = ctx.indicator('ema', period=ctx.params.get('fast_period', 5))\n    slow = ctx.indicator('ema', period=ctx.params.get('slow_period', 20))\n    if fast > slow:\n        ctx.buy()\n    elif fast < slow:\n        ctx.sell()\n`)
  const [symbol, setSymbol] = useState('600519')
  const [paramsJson, setParamsJson] = useState('{\n  "fast_period": 5,\n  "slow_period": 20\n}')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [error, setError] = useState('')

  const handleRun = async () => {
    setRunning(true)
    setError('')
    setResult(null)
    try {
      let params: Record<string, unknown> | undefined
      try { params = JSON.parse(paramsJson) } catch { /* ignore */ }
      const res = await strategyEngineApi.backtest({ code, symbol, params })
      setResult(res.data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '回测失败')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Left: Code + Params */}
      <div className="space-y-4">
        <div className="bg-bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-text-primary">策略代码</h3>
            <button
              onClick={handleRun}
              disabled={running}
              className={cn(
                'px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-200',
                'bg-accent text-white hover:bg-accent-light',
                'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                'disabled:opacity-50 flex items-center gap-1.5 shadow-sm'
              )}
            >
              {running ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              {running ? '运行中...' : '运行回测'}
            </button>
          </div>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full h-64 px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-xs font-mono resize-y transition-all duration-200 hover:border-border-focus focus:border-accent focus:outline-none"
            spellCheck={false}
          />
        </div>
        <div className="bg-bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-text-primary mb-3">回测参数</h3>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">股票代码</label>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="600519"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
              />
            </div>
          </div>
          <label className="text-xs text-text-tertiary mb-1 block">策略参数 (JSON)</label>
          <textarea
            value={paramsJson}
            onChange={(e) => setParamsJson(e.target.value)}
            className="w-full h-24 px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-xs font-mono resize-y transition-all duration-200 hover:border-border-focus focus:border-accent focus:outline-none"
            spellCheck={false}
          />
        </div>
        {error && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-danger-bg border border-danger/20 text-danger text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {error}
          </div>
        )}
      </div>

      {/* Right: Results */}
      <div className="space-y-4">
        {result && (
          <>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: '总收益', value: formatPercent(result.total_return), color: result.total_return >= 0 ? 'text-success' : 'text-danger' },
                { label: '最大回撤', value: formatPercent(-result.max_drawdown), color: 'text-danger' },
                { label: '夏普比率', value: result.sharpe_ratio.toFixed(2), color: 'text-text-primary' },
                { label: '胜率', value: formatPercent(result.win_rate), color: 'text-text-primary' },
              ].map((item) => (
                <div key={item.label} className="bg-bg-card border border-border rounded-xl p-4 card-hover">
                  <div className="text-xs text-text-tertiary mb-1">{item.label}</div>
                  <div className={cn('text-xl font-bold', item.color)}>{item.value}</div>
                </div>
              ))}
            </div>
            <div className="bg-bg-card border border-border rounded-xl p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3">权益曲线</h3>
              {result.equity_curve && result.equity_curve.length > 0 ? (
                <EquityChart data={result.equity_curve} />
              ) : (
                <div className="h-64 flex items-center justify-center text-text-tertiary text-sm">无权益曲线数据</div>
              )}
            </div>
            <div className="bg-bg-card border border-border rounded-xl p-4">
              <div className="text-xs text-text-tertiary mb-1">总交易次数</div>
              <div className="text-xl font-bold text-text-primary">{result.total_trades}</div>
            </div>
          </>
        )}
        {!result && !running && (
          <div className="bg-bg-card border border-border rounded-xl p-8 flex flex-col items-center justify-center text-text-tertiary">
            <FlaskConical className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">编写策略代码后点击「运行回测」查看结果</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Indicators Tab ──────────────────────────────────────────────────────────

function IndicatorsTab() {
  const [indicators, setIndicators] = useState<Indicator[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [execSymbol, setExecSymbol] = useState('600519')
  const [execResult, setExecResult] = useState<unknown>(null)
  const [execLoading, setExecLoading] = useState(false)

  useEffect(() => {
    strategyEngineApi.getIndicators()
      .then((res) => setIndicators(res.data?.indicators || res.data || []))
      .catch(() => setIndicators([]))
      .finally(() => setLoading(false))
  }, [])

  const handleExecute = async (name: string) => {
    setExecLoading(true)
    setExecResult(null)
    try {
      const res = await strategyEngineApi.executeIndicator(name, execSymbol)
      setExecResult(res.data)
    } catch {
      setExecResult({ error: '执行失败' })
    } finally {
      setExecLoading(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40 text-text-tertiary text-sm">加载中...</div>
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {indicators.map((ind) => (
          <div
            key={ind.name}
            className={cn('bg-bg-card border border-border rounded-xl p-4 card-hover cursor-pointer')}
            onClick={() => setExpanded(expanded === ind.name ? null : ind.name)}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="w-10 h-10 rounded-lg bg-accent-bg flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-accent" />
              </div>
              {expanded === ind.name ? <ChevronUp className="w-4 h-4 text-text-tertiary" /> : <ChevronDown className="w-4 h-4 text-text-tertiary" />}
            </div>
            <h3 className="font-semibold text-text-primary mb-1">{ind.name}</h3>
            <p className="text-xs text-text-tertiary mb-1">{ind.category}</p>
            <p className="text-sm text-text-secondary">{ind.description}</p>

            {expanded === ind.name && (
              <div className="mt-3 pt-3 border-t border-border space-y-3" onClick={(e) => e.stopPropagation()}>
                <div>
                  <label className="text-xs text-text-tertiary mb-1 block">股票代码</label>
                  <input
                    value={execSymbol}
                    onChange={(e) => setExecSymbol(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm"
                  />
                </div>
                <button
                  onClick={() => handleExecute(ind.name)}
                  disabled={execLoading}
                  className={cn(
                    'px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200',
                    'bg-accent text-white hover:bg-accent-light',
                    'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                    'disabled:opacity-50 flex items-center gap-1.5'
                  )}
                >
                  <Zap className="w-3.5 h-3.5" />
                  {execLoading ? '执行中...' : '执行'}
                </button>
                {execResult !== null && (
                  <pre className="text-xs text-text-secondary bg-bg-secondary rounded-lg p-2 overflow-x-auto max-h-32">
                    {JSON.stringify(execResult, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        ))}
        {indicators.length === 0 && (
          <div className="col-span-full flex flex-col items-center justify-center py-12 text-text-tertiary">
            <BarChart3 className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">暂无可用指标</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Running Tab ─────────────────────────────────────────────────────────────

function RunningTab() {
  const [strategies, setStrategies] = useState<StrategyListItem[]>([])
  const [metrics, setMetrics] = useState<Record<string, RuntimeMetrics>>({})
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const fetchStrategies = useCallback(async () => {
    try {
      const res = await strategyEngineApi.listStrategies()
      const list: StrategyListItem[] = res.data?.strategies || res.data || []
      setStrategies(list.filter((s) => s.status === 'running'))

      // Fetch metrics for each running strategy
      for (const s of list.filter((s) => s.status === 'running')) {
        try {
          const mRes = await strategyEngineApi.getRuntimeMetrics(s.id)
          setMetrics((prev) => ({ ...prev, [s.id]: mRes.data }))
        } catch { /* skip */ }
      }
    } catch {
      setStrategies([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchStrategies() }, [fetchStrategies])

  const handleStop = async (id: string) => {
    setActionLoading(id)
    try {
      await strategyEngineApi.stopStrategy(id)
      await fetchStrategies()
    } catch { /* silent */ }
    finally { setActionLoading(null) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40 text-text-tertiary text-sm">加载中...</div>
  }

  if (strategies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-tertiary">
        <Activity className="w-12 h-12 mb-3 opacity-30" />
        <p className="text-sm">暂无运行中的策略</p>
        <p className="text-xs mt-1">在策略库中启动策略后将在此显示</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {strategies.map((s) => {
        const m = metrics[s.id]
        return (
          <div key={s.id} className="bg-bg-card border border-border rounded-xl p-4 card-hover">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-success-bg flex items-center justify-center">
                  <Activity className="w-5 h-5 text-success" />
                </div>
                <div>
                  <h3 className="font-semibold text-text-primary">{s.name}</h3>
                  <p className="text-xs text-text-tertiary">{s.type} &middot; ID: {s.id}</p>
                </div>
              </div>
              <button
                onClick={() => handleStop(s.id)}
                disabled={actionLoading === s.id}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200',
                  'bg-danger-bg text-danger hover:bg-danger/20',
                  'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
                  'disabled:opacity-50 flex items-center gap-1.5'
                )}
              >
                <Square className="w-3.5 h-3.5" />
                {actionLoading === s.id ? '停止中...' : '停止'}
              </button>
            </div>
            {m && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  { label: '运行时间', value: `${Math.floor(m.uptime / 60)}分${m.uptime % 60}秒` },
                  { label: '处理 Ticks', value: m.ticks_processed.toLocaleString() },
                  { label: '生成信号', value: m.signals_generated.toLocaleString() },
                  { label: '最后 Tick', value: m.last_tick_at ? new Date(m.last_tick_at).toLocaleTimeString('zh-CN') : '--' },
                ].map((item) => (
                  <div key={item.label} className="bg-bg-secondary rounded-lg px-3 py-2">
                    <div className="text-[11px] text-text-tertiary">{item.label}</div>
                    <div className="text-sm font-medium text-text-primary">{item.value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Positions & Trades Tab ──────────────────────────────────────────────────

function PositionsTradesTab() {
  const [activeSubTab, setActiveSubTab] = useState<'positions' | 'trades'>('positions')
  const [positions, setPositions] = useState<StrategyPositionItem[]>([])
  const [trades, setTrades] = useState<StrategyTrade[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      strategyEngineApi.getPositions().catch(() => ({ data: [] })),
      strategyEngineApi.getTrades().catch(() => ({ data: [] })),
    ]).then(([posRes, tradeRes]) => {
      setPositions(posRes.data?.positions || posRes.data || [])
      setTrades(tradeRes.data?.trades || tradeRes.data || [])
    }).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-40 text-text-tertiary text-sm">加载中...</div>
  }

  return (
    <div className="space-y-4">
      {/* Sub-tabs */}
      <div className="flex items-center gap-1 border-b border-border">
        {[
          { key: 'positions' as const, label: '持仓', icon: Package },
          { key: 'trades' as const, label: '交易记录', icon: ListOrdered },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveSubTab(tab.key)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-all duration-200',
              activeSubTab === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            )}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Positions Table */}
      {activeSubTab === 'positions' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                {['策略', '代码', '方向', '数量', '入场价', '最高价', '最低价', '未实现盈亏', '更新时间'].map((h) => (
                  <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {positions.map((pos) => (
                <tr key={pos.id} className="hover:bg-bg-hover transition-colors duration-150">
                  <td className="px-4 py-3 text-text-secondary text-xs">{pos.strategy_id}</td>
                  <td className="px-4 py-3 text-text-primary font-medium">{pos.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      pos.side === 'long' ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                    )}>
                      {pos.side === 'long' ? '多' : '空'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-text-primary">{pos.size}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{pos.entry_price?.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{pos.highest_price?.toFixed(2) ?? '--'}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{pos.lowest_price?.toFixed(2) ?? '--'}</td>
                  <td className={cn('px-4 py-3 text-right font-medium', pos.unrealized_pnl >= 0 ? 'text-success' : 'text-danger')}>
                    {pos.unrealized_pnl >= 0 ? '+' : ''}{pos.unrealized_pnl.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-right text-text-tertiary text-xs">
                    {pos.updated_at ? new Date(pos.updated_at).toLocaleString('zh-CN') : '--'}
                  </td>
                </tr>
              ))}
              {positions.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-text-tertiary text-sm">暂无持仓</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Trades Table */}
      {activeSubTab === 'trades' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                {['时间', '代码', '方向', '价格', '数量', '盈亏'].map((h) => (
                  <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {trades.map((t) => (
                <tr key={t.id} className="hover:bg-bg-hover transition-colors duration-150">
                  <td className="px-4 py-3 text-text-secondary text-xs">{new Date(t.timestamp).toLocaleString('zh-CN')}</td>
                  <td className="px-4 py-3 text-text-primary font-medium">{t.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      t.side === 'buy' || t.side === 'open_long' ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                    )}>
                      {t.side === 'buy' || t.side === 'open_long' ? '买入' : '卖出'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-text-primary">{t.price.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{t.quantity}</td>
                  <td className={cn('px-4 py-3 text-right font-medium', t.pnl >= 0 ? 'text-success' : 'text-danger')}>
                    {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
              {trades.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-text-tertiary text-sm">暂无交易记录</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Library Tab ─────────────────────────────────────────────────────────────

function LibraryTab() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [symbol, setSymbol] = useState('600519')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ strategy: string; signal: StrategySignal } | null>(null)

  // ── 选股 / 筛选 ──
  const [toolMode, setToolMode] = useState<'pick' | 'screen'>('pick')
  const [pickSymbols, setPickSymbols] = useState('600519,000001,000002')
  const [selectedStrategy, setSelectedStrategy] = useState('ma_crossover')
  const [minConfidence, setMinConfidence] = useState(0.3)
  const [minPrice, setMinPrice] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [minChange, setMinChange] = useState('')
  const [maxChange, setMaxChange] = useState('')
  const [screenLimit, setScreenLimit] = useState('20')
  const [pickLoading, setPickLoading] = useState(false)
  const [pickResult, setPickResult] = useState<any>(null)
  const [screenResult, setScreenResult] = useState<any>(null)

  // ── AI 生成策略 ──
  const [customDesc, setCustomDesc] = useState('')
  const [customLoading, setCustomLoading] = useState(false)
  const [customResult, setCustomResult] = useState<any>(null)

  useEffect(() => {
    strategyApi.list().then((res) => {
      const list = res.data?.strategies || [
        { key: 'ma_crossover', name: '均线交叉', description: '基于短期与长期移动平均线的交叉信号' },
        { key: 'macd', name: 'MACD', description: '基于MACD指标的金叉死叉信号' },
        { key: 'rsi', name: 'RSI', description: '基于相对强弱指标的超买超卖信号' },
        { key: 'bollinger', name: '布林带', description: '基于布林带上下轨的突破信号' },
      ]
      setStrategies(list)
      if (list.length > 0) setSelectedStrategy(list[0].key)
    })
  }, [])

  const handleEvaluate = async (key: string) => {
    setLoading(true)
    try {
      const res = await strategyApi.evaluate(key, symbol)
      setResult({ strategy: key, signal: res.data?.signal || null })
    } catch {
      /* silent */
    } finally {
      setLoading(false)
    }
  }

  const handlePick = async () => {
    setPickLoading(true)
    setPickResult(null)
    setScreenResult(null)
    try {
      const symbols = pickSymbols.split(',').map((s) => s.trim()).filter(Boolean)
      const res = await strategyApi.pick(selectedStrategy, symbols, { min_confidence: minConfidence })
      setPickResult(res.data)
    } catch (err: any) {
      setPickResult({ error: err.message || '选股失败' })
    } finally {
      setPickLoading(false)
    }
  }

  const handleScreen = async () => {
    setPickLoading(true)
    setPickResult(null)
    setScreenResult(null)
    try {
      const filters: Record<string, unknown> = { limit: parseInt(screenLimit) || 20 }
      if (minPrice) filters.min_price = parseFloat(minPrice)
      if (maxPrice) filters.max_price = parseFloat(maxPrice)
      if (minChange) filters.min_change_pct = parseFloat(minChange)
      if (maxChange) filters.max_change_pct = parseFloat(maxChange)
      const res = await strategyApi.screen(filters)
      setScreenResult(res.data)
    } catch (err: any) {
      setScreenResult({ error: err.message || '筛选失败' })
    } finally {
      setPickLoading(false)
    }
  }

  const handleCreateCustom = async () => {
    if (!customDesc.trim()) return
    setCustomLoading(true)
    setCustomResult(null)
    try {
      const res = await strategyApi.createCustom(customDesc.trim())
      setCustomResult(res.data)
    } catch (err: any) {
      setCustomResult({ success: false, error: err.message || '生成失败' })
    } finally {
      setCustomLoading(false)
    }
  }

  return (
    <>
      <section className="mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-3">策略库</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {strategies.map((strategy) => (
            <StrategyCard
              key={strategy.key}
              strategy={strategy}
              onEvaluate={() => handleEvaluate(strategy.key)}
            />
          ))}
        </div>
      </section>

      {/* 选股 / 筛选 */}
      <section className="bg-bg-card border border-border rounded-xl p-4 mb-6 card-hover">
        <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
          <Search className="w-5 h-5 text-accent" />
          选股器
        </h2>

        {/* 模式切换 */}
        <div className="flex items-center gap-1 mb-4 border-b border-border">
          {[
            { key: 'pick' as const, label: '策略选股', icon: Brain },
            { key: 'screen' as const, label: '条件筛选', icon: Filter },
          ].map((m) => (
            <button
              key={m.key}
              onClick={() => setToolMode(m.key)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-all duration-200',
                toolMode === m.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              )}
            >
              <m.icon className="w-4 h-4" />
              {m.label}
            </button>
          ))}
        </div>

        {toolMode === 'pick' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">选择策略</label>
                <select
                  value={selectedStrategy}
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                >
                  {strategies.map((s) => (
                    <option key={s.key} value={s.key}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="text-xs text-text-tertiary mb-1 block">股票列表（逗号分隔）</label>
                <input
                  value={pickSymbols}
                  onChange={(e) => setPickSymbols(e.target.value)}
                  placeholder="如: 600519,000001,000002"
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">最小置信度: {(minConfidence * 100).toFixed(0)}%</label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minConfidence}
                onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
                className="w-full max-w-xs accent-accent"
              />
            </div>
            <button
              onClick={handlePick}
              disabled={pickLoading}
              className={cn(
                'px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium',
                'flex items-center gap-2 shadow-sm',
                'transition-all duration-200 hover:bg-accent-light hover:-translate-y-[1px] hover:shadow-md',
                'active:translate-y-0 active:scale-[0.985] disabled:opacity-50'
              )}
            >
              {pickLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              {pickLoading ? '选股中...' : '开始选股'}
            </button>
          </div>
        )}

        {toolMode === 'screen' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">最低价格</label>
                <input
                  type="number"
                  value={minPrice}
                  onChange={(e) => setMinPrice(e.target.value)}
                  placeholder="0"
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                />
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">最高价格</label>
                <input
                  type="number"
                  value={maxPrice}
                  onChange={(e) => setMaxPrice(e.target.value)}
                  placeholder="不限"
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                />
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">最小涨跌幅(%)</label>
                <input
                  type="number"
                  value={minChange}
                  onChange={(e) => setMinChange(e.target.value)}
                  placeholder="-10"
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                />
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">最大涨跌幅(%)</label>
                <input
                  type="number"
                  value={maxChange}
                  onChange={(e) => setMaxChange(e.target.value)}
                  placeholder="10"
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                />
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">返回数量</label>
                <input
                  type="number"
                  value={screenLimit}
                  onChange={(e) => setScreenLimit(e.target.value)}
                  placeholder="20"
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
                />
              </div>
            </div>
            <button
              onClick={handleScreen}
              disabled={pickLoading}
              className={cn(
                'px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium',
                'flex items-center gap-2 shadow-sm',
                'transition-all duration-200 hover:bg-accent-light hover:-translate-y-[1px] hover:shadow-md',
                'active:translate-y-0 active:scale-[0.985] disabled:opacity-50'
              )}
            >
              {pickLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Filter className="w-4 h-4" />}
              {pickLoading ? '筛选中...' : '开始筛选'}
            </button>
          </div>
        )}

        {/* 结果展示 */}
        {pickResult && !pickResult.error && (
          <div className="mt-4 space-y-3">
            <div className="text-xs text-text-tertiary">
              策略: {pickResult.strategy || selectedStrategy} &middot; 分析 {pickResult.total_analyzed} 只 &middot; 信号 {pickResult.signals_found} 个
            </div>
            {pickResult.buy_signals?.length > 0 && (
              <div>
                <div className="text-xs font-medium text-success mb-1">买入信号</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border-light text-text-tertiary">
                        <th className="text-left py-1.5 px-2 font-medium">代码</th>
                        <th className="text-left py-1.5 px-2 font-medium">名称</th>
                        <th className="text-right py-1.5 px-2 font-medium">置信度</th>
                        <th className="text-left py-1.5 px-2 font-medium">理由</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-light">
                      {pickResult.buy_signals.map((item: any, i: number) => (
                        <tr key={i} className="hover:bg-bg-hover">
                          <td className="py-1.5 px-2 text-text-primary font-mono">{item.symbol}</td>
                          <td className="py-1.5 px-2 text-text-primary">{item.name}</td>
                          <td className="py-1.5 px-2 text-right text-success font-medium">{(item.confidence * 100).toFixed(1)}%</td>
                          <td className="py-1.5 px-2 text-text-secondary text-xs max-w-xs truncate">{item.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {pickResult.sell_signals?.length > 0 && (
              <div>
                <div className="text-xs font-medium text-danger mb-1">卖出信号</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border-light text-text-tertiary">
                        <th className="text-left py-1.5 px-2 font-medium">代码</th>
                        <th className="text-left py-1.5 px-2 font-medium">名称</th>
                        <th className="text-right py-1.5 px-2 font-medium">置信度</th>
                        <th className="text-left py-1.5 px-2 font-medium">理由</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-light">
                      {pickResult.sell_signals.map((item: any, i: number) => (
                        <tr key={i} className="hover:bg-bg-hover">
                          <td className="py-1.5 px-2 text-text-primary font-mono">{item.symbol}</td>
                          <td className="py-1.5 px-2 text-text-primary">{item.name}</td>
                          <td className="py-1.5 px-2 text-right text-danger font-medium">{(item.confidence * 100).toFixed(1)}%</td>
                          <td className="py-1.5 px-2 text-text-secondary text-xs max-w-xs truncate">{item.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {pickResult?.error && (
          <div className="mt-4 p-3 rounded-xl bg-danger-bg border border-danger/20 text-danger text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {pickResult.error}
          </div>
        )}

        {screenResult && !screenResult.error && (
          <div className="mt-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-light text-text-tertiary">
                    <th className="text-left py-1.5 px-2 font-medium">代码</th>
                    <th className="text-left py-1.5 px-2 font-medium">名称</th>
                    <th className="text-right py-1.5 px-2 font-medium">最新价</th>
                    <th className="text-right py-1.5 px-2 font-medium">涨跌幅</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-light">
                  {Array.isArray(screenResult) ? screenResult.map((item: any, i: number) => (
                    <tr key={i} className="hover:bg-bg-hover">
                      <td className="py-1.5 px-2 text-text-primary font-mono">{item.symbol || item.代码}</td>
                      <td className="py-1.5 px-2 text-text-primary">{item.name || item.名称}</td>
                      <td className="py-1.5 px-2 text-right text-text-primary">{item.price || item.最新价}</td>
                      <td className={cn('py-1.5 px-2 text-right font-medium', (item.change_pct || item.涨跌幅) >= 0 ? 'text-success' : 'text-danger')}>
                        {(item.change_pct || item.涨跌幅) >= 0 ? '+' : ''}{item.change_pct || item.涨跌幅}%
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={4} className="py-4 px-2 text-text-tertiary text-sm">
                        <pre className="text-xs overflow-x-auto">{JSON.stringify(screenResult, null, 2)}</pre>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {screenResult?.error && (
          <div className="mt-4 p-3 rounded-xl bg-danger-bg border border-danger/20 text-danger text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {screenResult.error}
          </div>
        )}
      </section>

      {/* AI 生成策略 */}
      <section className="bg-bg-card border border-border rounded-xl p-4 mb-6 card-hover">
        <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-accent" />
          AI 生成策略
        </h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">用自然语言描述你的策略思路</label>
            <textarea
              value={customDesc}
              onChange={(e) => setCustomDesc(e.target.value)}
              placeholder="例如：当5日均线上穿20日均线且成交量放大2倍时买入，跌破10日均线时卖出..."
              className="w-full h-24 px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm resize-y transition-all duration-200 hover:border-border-focus focus:border-accent focus:outline-none"
              spellCheck={false}
            />
          </div>
          <button
            onClick={handleCreateCustom}
            disabled={customLoading || !customDesc.trim()}
            className={cn(
              'px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium',
              'flex items-center gap-2 shadow-sm',
              'transition-all duration-200 hover:bg-accent-light hover:-translate-y-[1px] hover:shadow-md',
              'active:translate-y-0 active:scale-[0.985] disabled:opacity-50'
            )}
          >
            {customLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {customLoading ? '生成中...' : '生成策略'}
          </button>
        </div>

        {customResult && (
          <div className="mt-4 space-y-3">
            {customResult.success ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-success">✓ 策略生成成功</span>
                  {customResult.strategy_key && (
                    <span className="text-xs text-text-tertiary font-mono">{customResult.strategy_key}</span>
                  )}
                </div>
                {customResult.code && (
                  <div>
                    <label className="text-xs text-text-tertiary mb-1 block">策略代码</label>
                    <pre className="text-xs text-text-secondary bg-bg-secondary rounded-lg p-3 overflow-x-auto max-h-64">
                      {customResult.code}
                    </pre>
                  </div>
                )}
              </>
            ) : (
              <div className="p-3 rounded-xl bg-danger-bg border border-danger/20 text-danger text-sm flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                {customResult.error || '生成失败'}
              </div>
            )}
          </div>
        )}
      </section>

      {result && (
        <section className="bg-bg-card border border-border rounded-xl p-4 card-hover animate-fade-in-up">
          <h3 className="font-semibold text-text-primary mb-2">策略分析结果</h3>
          <div className="flex items-center gap-4">
            <div className={cn(
              'px-3 py-1.5 rounded-lg text-sm font-medium',
              result.signal?.direction === 'buy' && 'bg-success-bg text-success',
              result.signal?.direction === 'sell' && 'bg-danger-bg text-danger',
              result.signal?.direction === 'hold' && 'bg-bg-secondary text-text-secondary'
            )}>
              {result.signal?.direction === 'buy' && '买入信号'}
              {result.signal?.direction === 'sell' && '卖出信号'}
              {result.signal?.direction === 'hold' && '观望'}
              {!result.signal?.direction && '无信号'}
            </div>
            {result.signal?.confidence != null && (
              <div className="text-sm text-text-secondary">
                置信度: {(result.signal.confidence * 100).toFixed(1)}%
              </div>
            )}
          </div>
          {result.signal?.reason && (
            <p className="text-sm text-text-secondary mt-2">{result.signal.reason}</p>
          )}
        </section>
      )}
    </>
  )
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function StrategyPage() {
  const [activeTab, setActiveTab] = useState<StrategyTab>('library')

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Tab Bar */}
      <div className="flex items-center gap-1 mb-4 border-b border-border overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-all duration-200 whitespace-nowrap',
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

      {/* Tab Content */}
      {activeTab === 'library' && <LibraryTab />}
      {activeTab === 'backtest' && <BacktestTab />}
      {activeTab === 'indicators' && <IndicatorsTab />}
      {activeTab === 'running' && <RunningTab />}
      {activeTab === 'positions' && <PositionsTradesTab />}
    </div>
  )
}

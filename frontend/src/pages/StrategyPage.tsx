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
  X,
  BookOpen,
  SlidersHorizontal,
  Lightbulb,
} from 'lucide-react'
import { strategyApi, strategyEngineApi, getErrorMessage } from '@/lib/api'
import type {
  StrategyInfo,
  StrategyListItem,
  BacktestResult,
  Indicator,
  StrategyPositionItem,
  StrategyTrade,
  RuntimeMetrics,
  EquityPoint,
} from '@/types'
import { cn, formatNumber, formatPercent, formatVolume } from '@/lib/utils'

type StrategyTab = 'library' | 'backtest' | 'indicators' | 'running' | 'positions'

const TABS = [
  { key: 'library' as const, label: '策略库', icon: Brain },
  { key: 'backtest' as const, label: '回测', icon: FlaskConical },
  { key: 'indicators' as const, label: '指标', icon: BarChart3 },
  { key: 'running' as const, label: '运行中', icon: Activity },
  { key: 'positions' as const, label: '持仓/交易', icon: Package },
]

// ── 策略详情数据 ────────────────────────────────────────────────────────────

const STRATEGY_DETAILS: Record<string, {
  overview: string
  algorithm: string
  params: { name: string; default: string; desc: string }[]
  signals: { condition: string; action: string }[]
}> = {
  ma_crossover: {
    overview: '均线交叉策略通过比较短期和长期移动平均线的位置关系，判断股价趋势的转折。当短期均线从下方穿越长期均线时，意味着短期趋势转强，形成「金叉」买入信号；反之则形成「死叉」卖出信号。',
    algorithm: '1. 计算 short_window 日简单移动平均（SMA）\n2. 计算 long_window 日简单移动平均（SMA）\n3. 比较当前和前一天的均线位置：\n   · 前一天 short < long 且 当天 short ≥ long → 金叉\n   · 前一天 short > long 且 当天 short ≤ long → 死叉',
    params: [
      { name: 'short_window', default: '5', desc: '短期均线周期，常用 5 日或 10 日' },
      { name: 'long_window', default: '20', desc: '长期均线周期，常用 20 日或 60 日' },
    ],
    signals: [
      { condition: '短期均线上穿长期均线（金叉）', action: '买入' },
      { condition: '短期均线下穿长期均线（死叉）', action: '卖出' },
      { condition: '均线未交叉', action: '观望' },
    ],
  },
  macd: {
    overview: 'MACD（指数平滑异同移动平均线）通过快慢两条指数移动平均线的差值（DIF）及其平滑线（DEA）的交叉关系，判断股价的趋势动量和转向时机。柱状图（Histogram）可辅助判断动能强弱。',
    algorithm: '1. 计算 fast 日 EMA 和 slow 日 EMA\n2. DIF = 快速 EMA − 慢速 EMA\n3. DEA（信号线）= DIF 的 signal 日 EMA\n4. Histogram（柱状图）= DIF − DEA\n5. 判断 DIF 与 DEA 的交叉情况',
    params: [
      { name: 'fast', default: '12', desc: '快速 EMA 周期' },
      { name: 'slow', default: '26', desc: '慢速 EMA 周期' },
      { name: 'signal', default: '9', desc: 'DEA（信号线）平滑周期' },
    ],
    signals: [
      { condition: 'DIF 上穿 DEA（金叉），柱状图红柱放大', action: '买入' },
      { condition: 'DIF 下穿 DEA（死叉），柱状图绿柱放大', action: '卖出' },
      { condition: 'DIF 与 DEA 未交叉', action: '观望' },
    ],
  },
  rsi: {
    overview: 'RSI（相对强弱指标）通过衡量一段时间内价格上涨与下跌的力度，判断股票是否处于超买或超卖状态。RSI 取值范围 0~100，常用于捕捉极端行情后的反转机会。',
    algorithm: '1. 计算周期内每日涨跌幅度\n2. 平均涨幅 = 上涨日涨幅均值（平滑处理）\n3. 平均跌幅 = 下跌日跌幅均值（平滑处理）\n4. RS = 平均涨幅 / 平均跌幅\n5. RSI = 100 − 100 / (1 + RS)\n6. 结合超卖/超买阈值和 RSI 趋势变化判断信号',
    params: [
      { name: 'period', default: '14', desc: 'RSI 计算周期，经典值为 14 日' },
      { name: 'oversold', default: '30', desc: '超卖阈值，低于此值视为超卖' },
      { name: 'overbought', default: '70', desc: '超买阈值，高于此值视为超买' },
    ],
    signals: [
      { condition: 'RSI 从超卖区（<30）回升', action: '买入' },
      { condition: 'RSI 从超买区（>70）回落', action: '卖出' },
      { condition: 'RSI 处于 30~70 之间', action: '观望' },
    ],
  },
  bollinger: {
    overview: '布林带策略通过股价与三条轨道线（上轨、中轨、下轨）的相对位置，判断价格的波动范围和突破/回归机会。价格触及轨道极值时往往预示着短期反转或趋势延续。',
    algorithm: '1. 中轨 = N 日简单移动平均线（SMA）\n2. 标准差 = N 日收盘价标准差\n3. 上轨 = 中轨 + K × 标准差\n4. 下轨 = 中轨 − K × 标准差\n5. 判断价格与上下轨的穿越/回归情况',
    params: [
      { name: 'period', default: '20', desc: '布林带计算周期，常用 20 日' },
      { name: 'std_dev', default: '2.0', desc: '标准差倍数，常用 2.0 倍' },
    ],
    signals: [
      { condition: '价格从下轨外反弹回轨道内', action: '买入' },
      { condition: '价格从上轨外回落回轨道内', action: '卖出' },
      { condition: '价格在轨道内运行', action: '观望' },
    ],
  },
}

// ── Strategy Detail Modal ───────────────────────────────────────────────────

function StrategyDetailModal({ strategy, currentParams, onClose }: {
  strategy: StrategyInfo | null
  currentParams: Record<string, number | string>
  onClose: () => void
}) {
  if (!strategy) return null
  const detail = STRATEGY_DETAILS[strategy.key]
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in"
      onClick={onClose}
    >
      {/* 半透明遮罩 */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      {/* 弹窗内容 */}
      <div
        className="relative w-full max-w-lg bg-bg-card border border-border rounded-2xl shadow-2xl overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-accent-bg flex items-center justify-center">
              <Brain className="w-4 h-4 text-accent" />
            </div>
            <h3 className="font-semibold text-text-primary">{strategy.name}</h3>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-secondary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 内容 */}
        <div className="px-5 py-4 space-y-5 max-h-[70vh] overflow-y-auto">
          {/* 简介 */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Lightbulb className="w-3.5 h-3.5 text-accent" />
              <span className="text-xs font-medium text-text-primary">策略简介</span>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">
              {detail?.overview || strategy.description}
            </p>
          </div>

          {/* 算法原理 */}
          {detail?.algorithm && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <BookOpen className="w-3.5 h-3.5 text-accent" />
                <span className="text-xs font-medium text-text-primary">算法原理</span>
              </div>
              <div className="bg-bg-secondary rounded-lg p-3 text-xs text-text-secondary leading-relaxed font-mono whitespace-pre-wrap">
                {detail.algorithm}
              </div>
            </div>
          )}

          {/* 参数说明 */}
          {detail?.params && detail.params.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <SlidersHorizontal className="w-3.5 h-3.5 text-accent" />
                <span className="text-xs font-medium text-text-primary">可调参数</span>
              </div>
              <div className="space-y-2">
                {detail.params.map((p) => (
                  <div key={p.name} className="flex items-start gap-3 bg-bg-secondary rounded-lg p-2.5">
                    <code className="text-xs font-mono text-accent bg-accent-bg px-1.5 py-0.5 rounded shrink-0">{p.name}</code>
                    <div className="min-w-0">
                      <div className="text-xs text-text-secondary">{p.desc}</div>
                      <div className="text-[11px] text-text-tertiary mt-0.5">默认值: {p.default}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 当前配置 */}
          {strategy.parameters && strategy.parameters.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <SlidersHorizontal className="w-3.5 h-3.5 text-accent" />
                <span className="text-xs font-medium text-text-primary">当前配置</span>
              </div>
              <div className="space-y-2">
                {strategy.parameters.map((p) => (
                  <div key={p.name} className="flex items-start gap-3 bg-bg-secondary rounded-lg p-2.5">
                    <code className="text-xs font-mono text-accent bg-accent-bg px-1.5 py-0.5 rounded shrink-0">{p.name}</code>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-text-secondary">{p.description}</div>
                      <div className="text-[11px] text-text-tertiary mt-0.5">
                        当前值: <span className="font-mono text-text-primary">{currentParams[p.name] ?? p.default}</span>
                        {p.min != null && p.max != null && `（范围 ${p.min}~${p.max}）`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 信号规则 */}
          {detail?.signals && detail.signals.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Activity className="w-3.5 h-3.5 text-accent" />
                <span className="text-xs font-medium text-text-primary">信号规则</span>
              </div>
              <div className="space-y-1.5">
                {detail.signals.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className={cn(
                      'px-1.5 py-0.5 rounded font-medium shrink-0',
                      s.action === '买入' && 'bg-success-bg text-success',
                      s.action === '卖出' && 'bg-danger-bg text-danger',
                      s.action === '观望' && 'bg-bg-secondary text-text-secondary'
                    )}>
                      {s.action}
                    </span>
                    <span className="text-text-secondary">{s.condition}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Strategy Config Modal ───────────────────────────────────────────────────

function StrategyConfigModal({ strategy, currentValues, onSave, onClose }: {
  strategy: StrategyInfo | null
  currentValues: Record<string, number | string>
  onSave: (values: Record<string, number | string>) => void
  onClose: () => void
}) {
  const [values, setValues] = useState<Record<string, number | string>>({})

  useEffect(() => {
    if (strategy) {
      const defaults: Record<string, number | string> = {}
      strategy.parameters?.forEach((p) => {
        defaults[p.name] = currentValues[p.name] ?? p.default
      })
      setValues(defaults)
    }
  }, [strategy, currentValues])

  if (!strategy) return null

  const handleChange = (name: string, val: string) => {
    const param = strategy.parameters?.find((p) => p.name === name)
    if (!param) return
    if (param.type === 'int') {
      // 只保留数字，去掉前导0
      const clean = val.replace(/\D/g, '').replace(/^0+/, '') || '0'
      setValues((prev) => ({ ...prev, [name]: parseInt(clean) }))
    } else if (param.type === 'float') {
      const clean = val.replace(/[^0-9.]/g, '').replace(/(\..*)\./g, '$1')
      setValues((prev) => ({ ...prev, [name]: parseFloat(clean) || 0 }))
    } else {
      setValues((prev) => ({ ...prev, [name]: val }))
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-md bg-bg-card border border-border rounded-2xl shadow-2xl overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-accent-bg flex items-center justify-center">
              <SlidersHorizontal className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h3 className="font-semibold text-text-primary text-sm">{strategy.name}</h3>
              <p className="text-[11px] text-text-tertiary">调整参数配置</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-secondary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 参数列表 */}
        <div className="px-5 py-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {strategy.parameters && strategy.parameters.length > 0 ? (
            strategy.parameters.map((param) => (
              <div key={param.name}>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-medium text-text-primary">
                    {param.name}
                  </label>
                  <span className="text-[10px] text-text-tertiary">
                    默认: {param.default}
                    {param.min != null && param.max != null && `（${param.min}~${param.max}）`}
                  </span>
                </div>
                <input
                  type="text"
                  inputMode={param.type === 'int' || param.type === 'float' ? 'numeric' : 'text'}
                  value={values[param.name] ?? ''}
                  onChange={(e) => handleChange(param.name, e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent focus:outline-none [appearance:textfield]"
                />
                <p className="text-[11px] text-text-tertiary mt-1">{param.description}</p>
              </div>
            ))
          ) : (
            <div className="text-center text-sm text-text-tertiary py-4">该策略暂无可调参数</div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-bg-secondary transition-colors"
          >
            取消
          </button>
          <button
            onClick={() => { onSave(values); onClose() }}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium bg-accent text-white hover:bg-accent-light',
              'transition-all duration-200 hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]'
            )}
          >
            保存配置
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Strategy Card ───────────────────────────────────────────────────────────

function StrategyCard({ strategy, onShowDetail, onShowConfig }: {
  strategy: StrategyInfo
  onShowDetail: () => void
  onShowConfig: () => void
}) {
  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 card-hover relative overflow-hidden transition-all duration-300">
      <div className="flex items-start justify-between mb-2">
        <div className="w-10 h-10 rounded-lg bg-accent-bg flex items-center justify-center">
          <Brain className="w-5 h-5 text-accent" />
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={(e) => { e.stopPropagation(); onShowConfig() }}
            className={cn(
              'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200',
              'bg-bg-secondary text-text-tertiary hover:text-accent hover:bg-accent-bg border border-border',
              'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
              'flex items-center gap-1'
            )}
            title="调整参数配置"
          >
            <SlidersHorizontal className="w-3 h-3" />
            调整配置
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onShowDetail() }}
            className={cn(
              'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200',
              'bg-accent/10 text-accent hover:bg-accent hover:text-white border border-accent/20',
              'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
              'flex items-center gap-1'
            )}
          >
            <BookOpen className="w-3 h-3" />
            策略详情
          </button>
        </div>
      </div>
      <h3 className="font-semibold text-text-primary mb-1">{strategy.name}</h3>
      <p className="text-sm text-text-secondary">{strategy.description}</p>
    </div>
  )
}

// ── Signal Table (公共组件) ───────────────────────────────────────────────

function SignalTable({ items, color }: { items: any[]; color: 'success' | 'danger' | 'neutral' }) {
  const colorMap = {
    success: { text: 'text-success', bg: 'bg-success', label: '买入' },
    danger: { text: 'text-danger', bg: 'bg-danger', label: '卖出' },
    neutral: { text: 'text-text-secondary', bg: 'bg-text-tertiary', label: '观望' },
  }
  const c = colorMap[color]
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-light text-text-tertiary">
            <th className="text-left py-1.5 px-2 font-medium w-[90px]">代码</th>
            <th className="text-left py-1.5 px-2 font-medium w-[100px]">名称</th>
            <th className="text-right py-1.5 px-2 font-medium w-[80px]">置信度</th>
            <th className="text-left py-1.5 px-2 font-medium">结论</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-light">
          {items.map((item: any, i: number) => (
            <tr key={i} className="hover:bg-bg-hover">
              <td className="py-1.5 px-2 text-text-primary font-mono">{item.symbol}</td>
              <td className="py-1.5 px-2 text-text-primary">{item.name || '-'}</td>
              <td className={cn('py-1.5 px-2 text-right font-medium', c.text)}>
                {(item.confidence * 100).toFixed(1)}%
              </td>
              <td className="py-1.5 px-2 text-text-secondary text-xs max-w-[280px] truncate">{item.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
      setError(getErrorMessage(err, '回测失败'))
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
                { label: '总收益', value: formatPercent(result.total_return), color: result.total_return >= 0 ? 'text-rise' : 'text-fall' },
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
      .then((res) => {
        const data = res.data || {}
        const builtin = (data.builtin || []).map((ind: any) => ({ ...ind, category: ind.category || '内置' }))
        const custom = (data.custom || []).map((ind: any) => ({ ...ind, category: ind.category || '自定义' }))
        setIndicators([...builtin, ...custom])
      })
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
      let posData = posRes.data?.positions ?? posRes.data ?? []
      let tradeData = tradeRes.data?.trades ?? tradeRes.data ?? []
      posData = Array.isArray(posData) ? posData : []
      tradeData = Array.isArray(tradeData) ? tradeData : []
      // 字段映射：后端 amount → 前端 size/quantity
      posData = posData.map((p: any) => ({ ...p, size: p.size ?? p.amount ?? 0 }))
      tradeData = tradeData.map((t: any) => ({ ...t, quantity: t.quantity ?? t.amount ?? 0 }))
      setPositions(posData)
      setTrades(tradeData)
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
                  <td className={cn('px-4 py-3 text-right font-medium', (pos.unrealized_pnl ?? 0) >= 0 ? 'text-rise' : 'text-fall')}>
                    {(pos.unrealized_pnl ?? 0) >= 0 ? '+' : ''}{formatNumber(pos.unrealized_pnl)}
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
                  <td className="px-4 py-3 text-text-secondary text-xs">
                    {t.timestamp ? new Date(t.timestamp).toLocaleString('zh-CN') : '--'}
                  </td>
                  <td className="px-4 py-3 text-text-primary font-medium">{t.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      /buy|open_long|add_long/i.test(t.side || '') ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                    )}>
                      {/buy|open_long|add_long/i.test(t.side || '') ? '买入' : '卖出'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-text-primary">{formatNumber(t.price)}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{t.quantity ?? '--'}</td>
                  <td className={cn('px-4 py-3 text-right font-medium', (t.pnl ?? 0) >= 0 ? 'text-rise' : 'text-fall')}>
                    {(t.pnl ?? 0) >= 0 ? '+' : ''}{formatNumber(t.pnl)}
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
  // ── 策略详情弹窗 ──
  const [detailStrategy, setDetailStrategy] = useState<StrategyInfo | null>(null)
  // ── 策略配置弹窗 ──
  const [configStrategy, setConfigStrategy] = useState<StrategyInfo | null>(null)
  const [strategyConfigs, setStrategyConfigs] = useState<Record<string, Record<string, number | string>>>({})

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
      // 后端直接返回数组，兼容两种格式
      const list: StrategyInfo[] = Array.isArray(res.data)
        ? res.data
        : res.data?.strategies || [
            { key: 'ma_crossover', name: '均线交叉', description: '基于短期与长期移动平均线的交叉信号', parameters: [
              { name: 'short_window', type: 'int', default: 5, min: 2, max: 60, description: '短期均线周期' },
              { name: 'long_window', type: 'int', default: 20, min: 5, max: 250, description: '长期均线周期' },
            ]},
            { key: 'macd', name: 'MACD', description: '基于MACD指标的金叉死叉信号', parameters: [
              { name: 'fast', type: 'int', default: 12, min: 5, max: 60, description: '快速 EMA 周期' },
              { name: 'slow', type: 'int', default: 26, min: 10, max: 120, description: '慢速 EMA 周期' },
              { name: 'signal', type: 'int', default: 9, min: 5, max: 60, description: '信号线(DEA)周期' },
            ]},
            { key: 'rsi', name: 'RSI', description: '基于相对强弱指标的超买超卖信号', parameters: [
              { name: 'period', type: 'int', default: 14, min: 5, max: 60, description: 'RSI 计算周期' },
              { name: 'oversold', type: 'int', default: 30, min: 10, max: 40, description: '超卖阈值' },
              { name: 'overbought', type: 'int', default: 70, min: 60, max: 90, description: '超买阈值' },
            ]},
            { key: 'bollinger', name: '布林带', description: '基于布林带上下轨的突破信号', parameters: [
              { name: 'period', type: 'int', default: 20, min: 5, max: 60, description: '布林带计算周期' },
              { name: 'std_dev', type: 'float', default: 2.0, min: 1.0, max: 4.0, description: '标准差倍数' },
            ]},
          ]
      setStrategies(list)
      if (list.length > 0) setSelectedStrategy(list[0].key)
    })
  }, [])

  const handlePick = async () => {
    setPickLoading(true)
    setPickResult(null)
    setScreenResult(null)
    try {
      const symbols = pickSymbols.split(',').map((s) => s.trim()).filter(Boolean)
      const params = strategyConfigs[selectedStrategy]
      const res = await strategyApi.pick(selectedStrategy, symbols, { min_confidence: minConfidence, params })
      setPickResult(res.data)
    } catch (err: any) {
      setPickResult({ error: getErrorMessage(err, '选股失败') })
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
      setScreenResult({ error: getErrorMessage(err, '筛选失败') })
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
      setCustomResult({ success: false, error: getErrorMessage(err, '生成失败') })
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
              onShowDetail={() => setDetailStrategy(strategy)}
              onShowConfig={() => setConfigStrategy(strategy)}
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
                {/* 策略说明 */}
                {strategies.length > 0 && (
                  <p className="text-[11px] text-text-tertiary mt-1.5 leading-relaxed">
                    {strategies.find((s) => s.key === selectedStrategy)?.description || ''}
                  </p>
                )}
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
                'px-4 py-2 rounded-lg text-sm font-medium',
                'bg-bg-secondary text-text-secondary hover:text-accent hover:bg-accent-bg border border-border',
                'flex items-center gap-2 shadow-sm',
                'transition-all duration-200 hover:-translate-y-[1px] hover:shadow-md',
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
                <p className="text-[10px] text-text-tertiary mt-1">数值即百分比，如 5 表示涨跌幅 ≥5%</p>
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
                'px-4 py-2 rounded-lg text-sm font-medium',
                'bg-bg-secondary text-text-secondary hover:text-accent hover:bg-accent-bg border border-border',
                'flex items-center gap-2 shadow-sm',
                'transition-all duration-200 hover:-translate-y-[1px] hover:shadow-md',
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
          <div className="mt-4 space-y-3 animate-fade-in-up">
            {/* 顶部统计摘要 */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-text-tertiary">
                策略 <span className="text-text-secondary font-medium">{pickResult.strategy || selectedStrategy}</span> 分析了 {pickResult.total_analyzed} 只股票
              </span>
              {(pickResult.buy_count > 0 || pickResult.sell_count > 0) && (
                <span className="text-text-tertiary">·</span>
              )}
              {pickResult.buy_count > 0 && (
                <span className="px-1.5 py-0.5 rounded bg-success-bg text-success font-medium">买入 {pickResult.buy_count}</span>
              )}
              {pickResult.sell_count > 0 && (
                <span className="px-1.5 py-0.5 rounded bg-danger-bg text-danger font-medium">卖出 {pickResult.sell_count}</span>
              )}
              {pickResult.hold_count > 0 && (
                <span className="px-1.5 py-0.5 rounded bg-bg-secondary text-text-secondary font-medium">观望 {pickResult.hold_count}</span>
              )}
              {pickResult.failed_count > 0 && (
                <span className="text-text-tertiary" title={pickResult.failed_symbols?.join(', ')}>
                  （{pickResult.failed_count} 只数据获取失败）
                </span>
              )}
            </div>

            {/* 买入信号 */}
            {pickResult.buy_signals?.length > 0 && (
              <div>
                <div className="text-xs font-medium text-success mb-1.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
                  买入信号 ({pickResult.buy_signals.length})
                </div>
                <SignalTable items={pickResult.buy_signals} color="success" />
              </div>
            )}

            {/* 卖出信号 */}
            {pickResult.sell_signals?.length > 0 && (
              <div>
                <div className="text-xs font-medium text-danger mb-1.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-danger inline-block" />
                  卖出信号 ({pickResult.sell_signals.length})
                </div>
                <SignalTable items={pickResult.sell_signals} color="danger" />
              </div>
            )}

            {/* 观望 / 无信号 */}
            {pickResult.hold_signals?.length > 0 && (
              <div>
                <div className="text-xs font-medium text-text-secondary mb-1.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-text-tertiary inline-block" />
                  观望 / 无信号 ({pickResult.hold_signals.length})
                </div>
                <SignalTable items={pickResult.hold_signals} color="neutral" />
              </div>
            )}

            {/* 全部无信号的空状态 */}
            {pickResult.buy_count === 0 && pickResult.sell_count === 0 && pickResult.hold_count > 0 && (
              <div className="p-4 rounded-xl bg-bg-secondary border border-border text-sm text-text-secondary animate-fade-in">
                <p className="mb-1">
                  <span className="font-medium text-text-primary">{pickResult.total_analyzed}</span> 只股票均未触发买入或卖出信号
                </p>
                <p className="text-xs text-text-tertiary">
                  {pickResult.hold_count} 只处于观望状态（如均线未交叉、无明显趋势）。你可以尝试换一组股票代码，或切换到其他策略。
                </p>
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
          <div className="mt-4 space-y-3 animate-fade-in-up">
            {/* 筛选说明 */}
            <div className="text-xs text-text-tertiary">
              在全市场 <span className="text-text-secondary font-medium">{screenResult.total_all?.toLocaleString() || '-'} 只</span> 股票中
              {screenResult.total_matched > 0 ? (
                <span>，按条件「<span className="text-text-secondary font-medium">{screenResult.conditions_text}</span>」找到 <span className="text-text-secondary font-medium">{screenResult.total_matched} 只</span></span>
              ) : (
                <span>，按条件「<span className="text-text-secondary font-medium">{screenResult.conditions_text}</span>」未找到符合条件的股票</span>
              )}
            </div>

            {/* 筛选结果表格 */}
            {screenResult.count > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-light text-text-tertiary">
                      <th className="text-left py-1.5 px-2 font-medium">代码</th>
                      <th className="text-left py-1.5 px-2 font-medium">名称</th>
                      <th className="text-right py-1.5 px-2 font-medium">最新价</th>
                      <th className="text-right py-1.5 px-2 font-medium">涨跌幅</th>
                      <th className="text-right py-1.5 px-2 font-medium">成交量</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-light">
                    {screenResult.stocks?.map((item: any, i: number) => (
                      <tr key={i} className="hover:bg-bg-hover">
                        <td className="py-1.5 px-2 text-text-primary font-mono">{item.symbol}</td>
                        <td className="py-1.5 px-2 text-text-primary">{item.name}</td>
                        <td className="py-1.5 px-2 text-right text-text-primary">{item.price != null ? `¥${Number(item.price).toFixed(2)}` : '-'}</td>
                        <td className={cn('py-1.5 px-2 text-right font-medium', (item.change_pct || 0) >= 0 ? 'text-rise' : 'text-fall')}>
                          {(item.change_pct || 0) >= 0 ? '+' : ''}{Number(item.change_pct).toFixed(2)}%
                        </td>
                        <td className="py-1.5 px-2 text-right text-text-secondary">{formatVolume(item.volume)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* 空结果友好提示 */}
            {screenResult.count === 0 && (
              <div className="p-4 rounded-xl bg-bg-secondary border border-border text-sm text-text-secondary animate-fade-in">
                <p className="mb-1 font-medium text-text-primary">未找到符合条件的股票</p>
                <p className="text-xs text-text-tertiary mb-2">
                  当前条件：{screenResult.conditions_text}
                </p>
                <p className="text-xs text-text-tertiary">
                  建议尝试放宽条件，如降低价格门槛、扩大涨跌幅范围，或减少筛选项。
                </p>
              </div>
            )}
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
              'px-4 py-2 rounded-lg text-sm font-medium',
              'bg-bg-secondary text-text-secondary hover:text-accent hover:bg-accent-bg border border-border',
              'flex items-center gap-2 shadow-sm',
              'transition-all duration-200 hover:-translate-y-[1px] hover:shadow-md',
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

      {/* 策略详情弹窗 */}
      {detailStrategy && (
        <StrategyDetailModal
          strategy={detailStrategy}
          currentParams={strategyConfigs[detailStrategy.key] || {}}
          onClose={() => setDetailStrategy(null)}
        />
      )}

      {/* 策略配置弹窗 */}
      {configStrategy && (
        <StrategyConfigModal
          strategy={configStrategy}
          currentValues={strategyConfigs[configStrategy.key] || {}}
          onSave={(values) => setStrategyConfigs((prev) => ({ ...prev, [configStrategy.key]: values }))}
          onClose={() => setConfigStrategy(null)}
        />
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

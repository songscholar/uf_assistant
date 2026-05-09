import { useState, useEffect, useCallback } from 'react'
import {
  BarChart3,
  Search,
  TrendingUp,
  Target,
  Brain,
  ChevronLeft,
  ChevronRight,
  Trash2,
  ChevronDown,
  ChevronUp,
  ThumbsUp,
  ThumbsDown,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import { analysisApi } from '@/lib/api'
import { cn, formatPercent } from '@/lib/utils'

interface AnalysisRecord {
  id: number
  market: string
  symbol: string
  signal: string
  decision?: string
  confidence: number
  summary: string
  indicators: Record<string, unknown>
  created_at: string
  user_feedback?: string
  price?: number | null
  // 详情字段（新记录才有）
  overall_rating?: string
  overall_score?: number
  score_breakdown?: Record<string, any>
  metrics_snapshot?: Record<string, any>
  trading_levels?: Record<string, any>
  key_reasons?: string[]
  risks?: string[]
  data_meta?: Record<string, any>
}

interface AnalysisStats {
  total_analyses: number
  avg_confidence: number
  signal_distribution: Record<string, number>
  accuracy_rate?: number
}

/* ── 分析详情卡片（复用于实时分析 + 历史详情） ── */
function AnalysisDetailCard({ data, title }: { data: any; title?: string }) {
  const normalizeConfidence = (confidence: number) => {
    const c = confidence || 0
    return c > 1 ? c / 100 : c
  }

  const signalBadge = (signal: string) => {
    const s = signal?.toUpperCase()
    return (
      <span className={cn(
        'px-2 py-0.5 rounded-md text-xs font-medium',
        s === 'BUY' && 'bg-success-bg text-success',
        s === 'SELL' && 'bg-danger-bg text-danger',
        s === 'HOLD' && 'bg-bg-secondary text-text-secondary',
        !['BUY', 'SELL', 'HOLD'].includes(s) && 'bg-bg-secondary text-text-tertiary'
      )}>
        {s || '--'}
      </span>
    )
  }

  // 数据获取失败提示
  const successModules = data.data_meta?.success || []
  const failedModules = data.data_meta?.failed || []
  const hasData = successModules.length > 0
  const allFailed = failedModules.length > 0 && successModules.length === 0

  return (
    <div className="mb-4 bg-bg-card border border-border rounded-xl p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-1.5">
            <Brain className="w-4 h-4 text-accent" />
            {title || data.symbol || '--'}
          </h3>
          {data.overall_rating && (
            <span className={cn(
              'px-2 py-0.5 rounded-md text-xs font-medium',
              (data.overall_score ?? 0) >= 20 ? 'bg-success-bg text-success' :
              (data.overall_score ?? 0) <= -20 ? 'bg-danger-bg text-danger' :
              'bg-bg-secondary text-text-secondary'
            )}>
              {data.overall_rating}
            </span>
          )}
        </div>
        <span className="text-xs text-text-tertiary">
          {data.created_at ? new Date(data.created_at).toLocaleString('zh-CN') : '刚刚'}
        </span>
      </div>

      {/* 数据获取失败警告 */}
      {allFailed && (
        <div className="bg-danger-bg/30 border border-danger/20 rounded-lg p-3 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-danger mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-danger">数据获取失败</div>
            <p className="text-xs text-text-secondary mt-0.5">
              无法获取该证券代码的行情数据，可能原因：代码不存在、非交易时间、或该代码类型暂不支持（如场外基金）。
            </p>
          </div>
        </div>
      )}

      {/* Key Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-bg-secondary rounded-lg p-3">
          <div className="text-xs text-text-tertiary mb-1">决策</div>
          {signalBadge(data.decision)}
        </div>
        <div className="bg-bg-secondary rounded-lg p-3">
          <div className="text-xs text-text-tertiary mb-1">置信度</div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-bg-card rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full',
                  normalizeConfidence(data.confidence) >= 0.7 ? 'bg-success' : normalizeConfidence(data.confidence) >= 0.4 ? 'bg-accent' : 'bg-danger'
                )}
                style={{ width: `${Math.min(100, normalizeConfidence(data.confidence) * 100)}%` }}
              />
            </div>
            <span className="text-xs font-medium text-text-primary">{(normalizeConfidence(data.confidence) * 100).toFixed(0)}%</span>
          </div>
        </div>
        <div className="bg-bg-secondary rounded-lg p-3">
          <div className="text-xs text-text-tertiary mb-1">综合评分</div>
          <span className={cn(
            'text-sm font-bold',
            (data.overall_score ?? 0) >= 20 ? 'text-success' :
            (data.overall_score ?? 0) <= -20 ? 'text-danger' : 'text-accent'
          )}>
            {(data.overall_score ?? 0).toFixed(1)}
          </span>
        </div>
        <div className="bg-bg-secondary rounded-lg p-3">
          <div className="text-xs text-text-tertiary mb-1">市场价</div>
          <span className="text-sm font-bold text-text-primary">
            {data.metrics_snapshot?.current_price?.toFixed(2) ??
             (data.price != null ? data.price.toFixed(2) : '--')}
          </span>
        </div>
        <div className="bg-bg-secondary rounded-lg p-3">
          <div className="text-xs text-text-tertiary mb-1">涨跌</div>
          <span className={cn(
            'text-sm font-bold',
            (data.metrics_snapshot?.change_percent ?? 0) >= 0 ? 'text-rise' : 'text-fall'
          )}>
            {(data.metrics_snapshot?.change_percent ?? 0) >= 0 ? '+' : ''}
            {(data.metrics_snapshot?.change_percent ?? 0).toFixed(2)}%
          </span>
        </div>
      </div>

      {/* Summary */}
      {data.summary && (
        <div className="bg-accent-bg/50 border border-accent/20 rounded-lg p-3">
          <div className="text-xs font-medium text-accent mb-1">分析摘要</div>
          <p className="text-sm text-text-primary leading-relaxed whitespace-pre-line">{data.summary}</p>
        </div>
      )}

      {/* Score Breakdown */}
      {data.score_breakdown && Object.keys(data.score_breakdown).length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-secondary mb-2">评分明细</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[
              { key: 'technical', label: '技术面', icon: TrendingUp },
              { key: 'fundamental', label: '基本面', icon: BarChart3 },
              { key: 'macro', label: '情绪面', icon: Target },
            ].map(({ key, label, icon: Icon }) => {
              const item = data.score_breakdown[key]
              if (!item) return null
              const s = item.score ?? 0
              return (
                <div key={key} className="bg-bg-secondary rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5">
                      <Icon className="w-3.5 h-3.5 text-text-tertiary" />
                      <span className="text-xs font-medium text-text-secondary">{label}</span>
                    </div>
                    <span className={cn(
                      'text-xs font-bold',
                      s >= 10 ? 'text-success' : s <= -10 ? 'text-danger' : 'text-text-secondary'
                    )}>
                      {s >= 0 ? '+' : ''}{s.toFixed(1)}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {item.details?.slice(0, 3).map((d: string, i: number) => (
                      <div key={i} className="text-xs text-text-secondary leading-relaxed flex items-start gap-1">
                        <span className="text-text-tertiary mt-0.5">•</span>
                        {d}
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Key Metrics */}
      {data.metrics_snapshot && Object.keys(data.metrics_snapshot).length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-secondary mb-2">关键指标</div>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
            {[
              { label: 'RSI(14)', value: data.metrics_snapshot.rsi?.toFixed(1) ?? '--', highlight: true },
              { label: 'MACD', value: data.metrics_snapshot.macd_signal ?? '--' },
              { label: 'MA趋势', value: data.metrics_snapshot.ma_trend ?? '--' },
              { label: '市盈率', value: data.metrics_snapshot.pe_ratio?.toFixed(1) ?? '--' },
              { label: '市净率', value: data.metrics_snapshot.pb_ratio?.toFixed(2) ?? '--' },
              { label: '换手率', value: data.metrics_snapshot.turnover_rate ? `${data.metrics_snapshot.turnover_rate.toFixed(2)}%` : '--' },
              { label: '支撑位', value: data.metrics_snapshot.support?.toFixed(2) ?? '--' },
              { label: '阻力位', value: data.metrics_snapshot.resistance?.toFixed(2) ?? '--' },
              { label: '波动率', value: data.metrics_snapshot.volatility_pct ? `${data.metrics_snapshot.volatility_pct.toFixed(1)}%` : '--' },
              { label: '量比', value: data.metrics_snapshot.volume_ratio?.toFixed(2) ?? '--' },
              { label: '价格位置', value: data.metrics_snapshot.price_position ? `${data.metrics_snapshot.price_position.toFixed(0)}%` : '--' },
              { label: '布林带', value: data.metrics_snapshot.bollinger_upper && data.metrics_snapshot.bollinger_lower ? `${data.metrics_snapshot.bollinger_lower.toFixed(1)}-${data.metrics_snapshot.bollinger_upper.toFixed(1)}` : '--' },
            ].map((m) => (
              <div key={m.label} className="bg-bg-secondary rounded-lg p-2 text-center">
                <div className="text-[10px] text-text-tertiary mb-0.5">{m.label}</div>
                <div className={cn('text-xs font-semibold', m.highlight ? 'text-accent' : 'text-text-primary')}>
                  {m.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trading Levels */}
      {data.trading_levels && Object.keys(data.trading_levels).length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-secondary mb-2">交易建议</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {[
              { label: '参考入场价', value: data.trading_levels.entry_price, color: 'text-accent' },
              { label: '止损价', value: data.trading_levels.stop_loss, color: 'text-danger' },
              { label: '目标价', value: data.trading_levels.take_profit, color: 'text-success' },
              { label: '盈亏比', value: data.trading_levels.risk_reward, color: 'text-text-primary' },
            ].map((t) => (
              <div key={t.label} className="bg-bg-secondary rounded-lg p-2 text-center">
                <div className="text-[10px] text-text-tertiary mb-0.5">{t.label}</div>
                <div className={cn('text-xs font-bold', t.color)}>
                  {t.value != null ? (typeof t.value === 'number' ? t.value.toFixed(2) : t.value) : '--'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key Reasons & Risks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {data.key_reasons && data.key_reasons.length > 0 && (
          <div className="bg-success-bg/30 border border-success/20 rounded-lg p-3">
            <div className="text-xs font-medium text-success mb-2">看多理由</div>
            <div className="space-y-1">
              {data.key_reasons.map((r: string, i: number) => (
                <div key={i} className="text-xs text-text-primary flex items-start gap-1">
                  <span className="text-success mt-0.5">+</span>
                  {r}
                </div>
              ))}
            </div>
          </div>
        )}
        {data.risks && data.risks.length > 0 && (
          <div className="bg-danger-bg/30 border border-danger/20 rounded-lg p-3">
            <div className="text-xs font-medium text-danger mb-2">风险提示</div>
            <div className="space-y-1">
              {data.risks.map((r: string, i: number) => (
                <div key={i} className="text-xs text-text-primary flex items-start gap-1">
                  <span className="text-danger mt-0.5">-</span>
                  {r}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── 主页面 ── */
export default function AnalysisPage() {
  const [records, setRecords] = useState<AnalysisRecord[]>([])
  const [stats, setStats] = useState<AnalysisStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [searchSymbol, setSearchSymbol] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<any>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [historyRes, statsRes] = await Promise.all([
        analysisApi.getHistory({ page, limit: 15, symbol: searchQuery || undefined }).catch(() => ({ data: { data: { items: [], total: 0 } } })),
        analysisApi.getStats().catch(() => ({ data: { data: {} } })),
      ])

      const historyData = historyRes.data?.data || historyRes.data || {}
      setRecords(historyData.items || historyData.records || [])
      const total = historyData.total || 0
      setTotalPages(Math.max(1, Math.ceil(total / 15)))

      const statsData = statsRes.data?.data || statsRes.data || {}
      setStats(statsData.total_analyses != null ? statsData : null)
    } catch {
      setRecords([])
    } finally {
      setLoading(false)
    }
  }, [page, searchQuery])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSearch = () => {
    setPage(1)
    setSearchQuery(searchSymbol)
    setAnalysisResult(null)
  }

  const handleAnalyze = async () => {
    if (!searchSymbol.trim()) return
    setAnalyzing(true)
    setAnalysisResult(null)
    setExpandedId(null)
    try {
      const symbol = searchSymbol.trim().toUpperCase()
      const res = await analysisApi.analyze(symbol)
      const data = res.data?.data || res.data
      setAnalysisResult(data)
      // 不自动加载历史记录（用户手动点击"搜索历史"才加载）
    } catch (err: any) {
      setAnalysisResult({ error: err.response?.data?.detail || '分析失败' })
    } finally {
      setAnalyzing(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await analysisApi.delete(String(id))
      setRecords((prev) => prev.filter((r) => r.id !== id))
    } catch { /* silent */ }
  }

  const [feedbackMap, setFeedbackMap] = useState<Record<number, 'helpful' | 'not_helpful'>>({})

  const handleFeedback = async (id: number, feedback: 'helpful' | 'not_helpful') => {
    try {
      await analysisApi.feedback(id, feedback)
      setFeedbackMap((prev) => ({ ...prev, [id]: feedback }))
    } catch {
      /* silent */
    }
  }

  // 点击历史记录行：手风琴展开/折叠详情
  const handleRecordClick = (record: AnalysisRecord) => {
    if (expandedId === record.id) {
      setExpandedId(null)
    } else {
      setExpandedId(record.id)
    }
  }

  const signalBadge = (signal: string) => {
    const s = signal?.toUpperCase()
    return (
      <span className={cn(
        'px-2 py-0.5 rounded-md text-xs font-medium',
        s === 'BUY' && 'bg-success-bg text-success',
        s === 'SELL' && 'bg-danger-bg text-danger',
        s === 'HOLD' && 'bg-bg-secondary text-text-secondary',
        !['BUY', 'SELL', 'HOLD'].includes(s) && 'bg-bg-secondary text-text-tertiary'
      )}>
        {s || '--'}
      </span>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Stats Cards */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {[
          { label: '总分析次数', value: stats?.total_analyses?.toLocaleString() ?? '--', icon: BarChart3 },
          { label: '平均置信度', value: stats?.avg_confidence != null ? `${Math.round(stats.avg_confidence)}%` : '--', icon: Target },
          { label: '买入信号', value: stats?.signal_distribution?.BUY?.toLocaleString() ?? '--', icon: TrendingUp },
          { label: '卖出信号', value: stats?.signal_distribution?.SELL?.toLocaleString() ?? '--', icon: TrendingUp },
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

      {/* Search & Analyze */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex-1 max-w-xs relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
          <input
            value={searchSymbol}
            onChange={(e) => setSearchSymbol(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="输入股票代码..."
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
          />
        </div>
        <button
          onClick={handleSearch}
          className={cn(
            'px-4 py-2 rounded-lg bg-bg-card border border-border text-text-primary text-sm font-medium',
            'flex items-center gap-1.5',
            'transition-all duration-200 hover:bg-bg-hover hover:-translate-y-[1px]',
            'active:translate-y-0 active:scale-[0.985]'
          )}
        >
          <Search className="w-4 h-4" />
          搜索历史
        </button>
        <button
          onClick={handleAnalyze}
          disabled={analyzing || !searchSymbol.trim()}
          className={cn(
            'px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium',
            'flex items-center gap-1.5 shadow-sm',
            'transition-all duration-200 hover:bg-accent-light hover:-translate-y-[1px]',
            'active:translate-y-0 active:scale-[0.985]',
            'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0'
          )}
        >
          {analyzing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Brain className="w-4 h-4" />
          )}
          {analyzing ? '分析中...' : '执行 AI 分析'}
        </button>
      </div>

      {/* Analysis Result (实时分析) */}
      {analysisResult && !analysisResult.error && (
        <AnalysisDetailCard data={analysisResult} />
      )}

      {/* Error */}
      {analysisResult?.error && (
        <div className="mb-4 bg-danger-bg/30 border border-danger/20 rounded-xl p-4 flex items-center gap-2 text-sm text-danger">
          <AlertCircle className="w-4 h-4" />
          {analysisResult.error}
        </div>
      )}

      {/* History Table */}
      <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg-secondary text-text-secondary text-xs">
              {['代码', '市场', '信号', '置信度', '摘要', '时间', '操作'].map((h) => (
                <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-text-tertiary text-sm">加载中...</td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-text-tertiary text-sm">
                  <Brain className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  暂无分析记录
                </td>
              </tr>
            ) : (
              records.map((record) => (
                <>
                  <tr
                    key={record.id}
                    className="hover:bg-bg-hover transition-colors duration-150 cursor-pointer"
                    onClick={() => handleRecordClick(record)}
                  >
                    <td className="px-4 py-3 text-text-primary font-medium">{record.symbol}</td>
                    <td className="px-4 py-3 text-text-secondary text-xs">{record.market}</td>
                    <td className="px-4 py-3">{signalBadge(record.signal)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-bg-secondary rounded-full overflow-hidden max-w-[80px]">
                          <div
                            className={cn(
                              'h-full rounded-full transition-all duration-300',
                              record.confidence >= 0.7 ? 'bg-success' : record.confidence >= 0.4 ? 'bg-accent' : 'bg-danger'
                            )}
                            style={{ width: `${Math.min(100, (record.confidence || 0) * 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-text-secondary">{((record.confidence || 0) * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-text-secondary text-xs max-w-[300px] truncate">{record.summary}</td>
                    <td className="px-4 py-3 text-text-tertiary text-xs whitespace-nowrap">
                      {record.created_at ? new Date(record.created_at).toLocaleString('zh-CN') : '--'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                        {expandedId === record.id ? (
                          <ChevronUp className="w-4 h-4 text-text-tertiary" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-text-tertiary" />
                        )}
                        <button
                          onClick={() => handleDelete(record.id)}
                          className="p-1 rounded-md hover:bg-bg-hover text-text-tertiary hover:text-danger transition-all"
                          title="删除"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedId === record.id && (
                    <tr key={`${record.id}-detail`}>
                      <td colSpan={7} className="px-4 py-4 bg-bg-secondary/50">
                        {/* 新记录有完整详情字段，复用 AnalysisDetailCard */}
                        {(record.score_breakdown || record.metrics_snapshot) ? (
                          <AnalysisDetailCard
                            data={{
                              symbol: record.symbol,
                              decision: record.decision || record.signal,
                              confidence: record.confidence != null ? record.confidence * 100 : 50,
                              overall_rating: record.overall_rating,
                              overall_score: record.overall_score,
                              summary: record.summary,
                              score_breakdown: record.score_breakdown,
                              metrics_snapshot: record.metrics_snapshot,
                              trading_levels: record.trading_levels,
                              key_reasons: record.key_reasons,
                              risks: record.risks,
                              data_meta: record.data_meta,
                              created_at: record.created_at,
                              price: record.price,
                            }}
                          />
                        ) : (
                          /* 旧记录没有详情字段，只展示简要信息 */
                          <div className="space-y-3">
                            <div>
                              <div className="text-xs text-text-tertiary mb-1">完整分析</div>
                              <p className="text-sm text-text-primary">{record.summary || '无详细分析'}</p>
                            </div>
                            {record.indicators && Object.keys(record.indicators).length > 0 && (
                              <div>
                                <div className="text-xs text-text-tertiary mb-1">技术指标</div>
                                <div className="flex flex-wrap gap-2">
                                  {Object.entries(record.indicators).map(([k, v]) => (
                                    <span key={k} className="px-2 py-0.5 rounded bg-bg-card border border-border text-xs text-text-secondary">
                                      {k}: {typeof v === 'number' ? v.toFixed(2) : String(v)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                        {/* 反馈按钮 */}
                        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border-light">
                          <span className="text-xs text-text-tertiary">这个分析有用吗？</span>
                          <button
                            onClick={() => handleFeedback(record.id, 'helpful')}
                            className={cn(
                              'p-1 rounded transition-all',
                              (feedbackMap[record.id] ?? record.user_feedback) === 'helpful'
                                ? 'bg-success-bg text-success'
                                : 'text-text-tertiary hover:bg-success-bg hover:text-success'
                            )}
                            title="有帮助"
                          >
                            <ThumbsUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleFeedback(record.id, 'not_helpful')}
                            className={cn(
                              'p-1 rounded transition-all',
                              (feedbackMap[record.id] ?? record.user_feedback) === 'not_helpful'
                                ? 'bg-danger-bg text-danger'
                                : 'text-text-tertiary hover:bg-danger-bg hover:text-danger'
                            )}
                            title="没帮助"
                          >
                            <ThumbsDown className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
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
          <span className="text-sm text-text-secondary px-3">
            {page} / {totalPages}
          </span>
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

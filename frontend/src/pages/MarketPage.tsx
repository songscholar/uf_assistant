import { useState, useEffect, useCallback, useRef } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Flame,
  ArrowUpRight,
  RefreshCw,
  AlertTriangle,
  Clock,
  BarChart3,
  Swords,
  Star,
  Trash2,
  Plus,
} from 'lucide-react'
import { marketApi, stockApi } from '@/lib/api'
import type { MarketIndex, SectorData } from '@/types'
import { cn, formatNumber, formatPercent } from '@/lib/utils'

function IndexCard({ index }: { index: MarketIndex }) {
  const isUp = index.change >= 0
  return (
    <div
      className={cn(
        'bg-bg-card border border-border rounded-xl p-4',
        'card-hover cursor-pointer'
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-secondary">{index.name}</span>
          {index.market && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-hover text-text-tertiary">{index.market}</span>
          )}
        </div>
        {isUp ? (
          <TrendingUp className="w-4 h-4 text-rise" />
        ) : (
          <TrendingDown className="w-4 h-4 text-fall" />
        )}
      </div>
      <div className="text-2xl font-bold text-text-primary mb-1">
        {formatNumber(index.value)}
      </div>
      <div className={cn('text-sm font-medium', isUp ? 'text-rise' : 'text-fall')}>
        {isUp ? '▲' : '▼'} {formatPercent(index.change_percent)}
      </div>
    </div>
  )
}

function SectorRow({ sector, rank }: { sector: SectorData; rank: number }) {
  const isUp = sector.change_percent >= 0
  return (
    <div className="flex items-center justify-between py-2.5 px-3 rounded-lg hover:bg-bg-hover transition-all duration-200 cursor-pointer">
      <div className="flex items-center gap-3">
        <span className="w-5 text-xs text-text-tertiary text-center font-mono">{rank}</span>
        <span className="text-sm text-text-primary">{sector.name}</span>
      </div>
      <span className={cn('text-sm font-medium', isUp ? 'text-rise' : 'text-fall')}>
        {isUp ? '+' : ''}{sector.change_percent.toFixed(2)}%
      </span>
    </div>
  )
}

function DataSourceBadge({
  source,
  timestamp,
  isLoading,
}: {
  source: 'live' | 'demo' | 'unknown'
  timestamp: string
  isLoading: boolean
}) {
  const timeStr = timestamp
    ? new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '--:--:--'

  if (isLoading) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-text-tertiary">
        <RefreshCw className="w-3 h-3 animate-spin" />
        更新中...
      </span>
    )
  }

  if (source === 'demo') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-500">
        <AlertTriangle className="w-3 h-3" />
        模拟数据
        <span className="text-text-tertiary ml-1">{timeStr}</span>
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1 text-xs text-success">
      <Clock className="w-3 h-3" />
      实时 {timeStr}
    </span>
  )
}

const REFRESH_INTERVAL = 30000 // 30 秒

export default function MarketPage() {
  const [indices, setIndices] = useState<MarketIndex[]>([])
  const [sectors, setSectors] = useState<SectorData[]>([])
  const [northbound, setNorthbound] = useState<any>(null)
  const [overview, setOverview] = useState<any>(null)
  const [longhu, setLonghu] = useState<any>(null)
  const [watchlist, setWatchlist] = useState<any[]>([])
  const [watchlistInput, setWatchlistInput] = useState('')
  const [watchlistLoading, setWatchlistLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [dataSource, setDataSource] = useState<'live' | 'demo' | 'unknown'>('unknown')
  const [lastUpdated, setLastUpdated] = useState('')
  const [error, setError] = useState('')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchWatchlist = useCallback(async () => {
    try {
      const res = await stockApi.getWatchlist()
      setWatchlist(res.data?.items || [])
    } catch {
      setWatchlist([])
    }
  }, [])

  const handleAddWatchlist = async () => {
    const symbol = watchlistInput.trim()
    if (!symbol) return
    setWatchlistLoading(true)
    try {
      await stockApi.addWatchlist(symbol)
      setWatchlistInput('')
      await fetchWatchlist()
    } catch (err: any) {
      alert(err.response?.data?.detail || '添加失败')
    } finally {
      setWatchlistLoading(false)
    }
  }

  const handleDeleteWatchlist = async (symbol: string) => {
    try {
      await stockApi.deleteWatchlist(symbol)
      await fetchWatchlist()
    } catch {
      /* silent */
    }
  }

  const fetchData = useCallback(async (isBackground = false) => {
    if (!isBackground) setLoading(true)
    else setRefreshing(true)
    setError('')

    // 每个接口独立请求，失败互不影响
    const [indicesRes, sectorsRes, northboundRes, overviewRes, longhuRes] = await Promise.all([
      marketApi.getIndices().catch(() => ({ data: null })),
      marketApi.getSectors().catch(() => ({ data: null })),
      marketApi.getNorthbound().catch(() => ({ data: null })),
      marketApi.getOverview().catch(() => ({ data: null })),
      marketApi.getLonghu().catch(() => ({ data: null })),
    ])

    const idxData = indicesRes?.data || {}
    const secData = sectorsRes?.data || {}
    const nbData = northboundRes?.data || null
    const ovData = overviewRes?.data || null
    const lhData = longhuRes?.data || null

    // 只有成功获取到数据才更新状态
    if (idxData && idxData.indices) setIndices(idxData.indices)
    if (secData && secData.sectors) setSectors(secData.sectors)
    if (nbData) setNorthbound(nbData)
    if (ovData) setOverview(ovData)
    if (lhData) setLonghu(lhData)

    // 根据有数据的接口判断来源
    const hasLive = idxData?.source === 'live' || secData?.source === 'live'
    const hasDemo = idxData?.source === 'demo' || secData?.source === 'demo'
    if (hasLive) setDataSource('live')
    else if (hasDemo) setDataSource('demo')
    setLastUpdated(idxData?.timestamp || new Date().toISOString())

    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    fetchData()
    fetchWatchlist()

    intervalRef.current = setInterval(() => {
      fetchData(true)
      fetchWatchlist()
    }, REFRESH_INTERVAL)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchData, fetchWatchlist])

  if (loading && !refreshing) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="animate-shimmer w-8 h-8 rounded-full" />
      </div>
    )
  }

  const summary = overview?.summary || {}

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Header with refresh */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-text-primary">市场行情</h2>
          <DataSourceBadge source={dataSource} timestamp={lastUpdated} isLoading={refreshing} />
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                     bg-bg-hover text-text-secondary hover:bg-bg-active hover:text-text-primary
                     transition-smooth disabled:opacity-50"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', refreshing && 'animate-spin')} />
          刷新
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-danger/10 border border-danger/20 text-danger text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      {dataSource === 'demo' && (
        <div className="mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-600 text-sm flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            当前展示的是模拟数据，非真实市场行情。数据源服务暂时不可用（可能是网络问题或非交易时间）。
            系统每 30 秒会自动重试获取真实数据。
          </div>
        </div>
      )}

      {/* Market Overview */}
      {overview && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-accent" />
            市场概况
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {[
              { label: '上涨', value: summary.up || 0, color: 'text-rise', bg: 'bg-rise/10' },
              { label: '下跌', value: summary.down || 0, color: 'text-fall', bg: 'bg-fall/10' },
              { label: '平盘', value: summary.flat || 0, color: 'text-text-secondary', bg: 'bg-bg-hover' },
              { label: '涨停', value: summary.limit_up || 0, color: 'text-rise', bg: 'bg-rise/10' },
              { label: '跌停', value: summary.limit_down || 0, color: 'text-fall', bg: 'bg-fall/10' },
            ].map((item) => (
              <div key={item.label} className={cn('border border-border rounded-xl p-4 card-hover', item.bg)}>
                <div className="text-xs text-text-tertiary mb-1">{item.label}</div>
                <div className={cn('text-2xl font-bold', item.color)}>{item.value}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Activity className="w-5 h-5 text-accent" />
          大盘指数
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {indices.length > 0 ? (
            indices.map((index) => <IndexCard key={index.symbol} index={index} />)
          ) : (
            <div className="col-span-full text-center py-8 text-text-tertiary text-sm">暂无指数数据</div>
          )}
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="bg-bg-card border border-border rounded-xl p-4 card-hover">
          <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Flame className="w-5 h-5 text-accent" />
            板块热点
          </h2>
          <div className="divide-y divide-border-light">
            {sectors.length > 0 ? (
              sectors.map((sector, i) => (
                <SectorRow key={sector.name} sector={sector} rank={i + 1} />
              ))
            ) : (
              <div className="text-center py-8 text-text-tertiary text-sm">暂无板块数据</div>
            )}
          </div>
        </section>

        <section className="bg-bg-card border border-border rounded-xl p-4 card-hover">
          <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
            <ArrowUpRight className="w-5 h-5 text-accent" />
            北向资金
          </h2>
          {northbound?.flow?.length > 0 ? (
            <div className="divide-y divide-border-light">
              {northbound.flow.map((item: any, i: number) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-2.5 px-3 rounded-lg hover:bg-bg-hover transition-all duration-200"
                >
                  <span className="text-sm text-text-secondary">{item.date}</span>
                  <span
                    className={cn(
                      'text-sm font-medium',
                      item.net_inflow >= 0 ? 'text-rise' : 'text-fall'
                    )}
                  >
                    {item.net_inflow >= 0 ? '+' : ''}
                    {item.net_inflow} 亿
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-text-tertiary text-sm">暂无北向资金数据</div>
          )}
        </section>
      </div>

      {/* 自选股票 */}
      <section className="mt-6 bg-bg-card border border-border rounded-xl p-4 card-hover">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Star className="w-5 h-5 text-accent" />
            自选股票
          </h2>
          <div className="flex items-center gap-2">
            <input
              value={watchlistInput}
              onChange={(e) => setWatchlistInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddWatchlist()}
              placeholder="输入代码如 600519"
              className="w-32 px-2.5 py-1.5 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent focus:outline-none"
            />
            <button
              onClick={handleAddWatchlist}
              disabled={watchlistLoading || !watchlistInput.trim()}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium',
                'bg-bg-secondary text-text-secondary hover:text-accent hover:bg-accent-bg border border-border',
                'flex items-center gap-1 transition-all duration-200',
                'disabled:opacity-50'
              )}
            >
              {watchlistLoading ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
              添加
            </button>
          </div>
        </div>
        {watchlist.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-light text-text-tertiary">
                  <th className="text-left py-2 px-3 font-medium">代码</th>
                  <th className="text-left py-2 px-3 font-medium">名称</th>
                  <th className="text-right py-2 px-3 font-medium">最新价</th>
                  <th className="text-right py-2 px-3 font-medium">涨跌额</th>
                  <th className="text-right py-2 px-3 font-medium">涨跌幅</th>
                  <th className="text-right py-2 px-3 font-medium">添加价格</th>
                  <th className="text-right py-2 px-3 font-medium">自添加涨跌幅</th>
                  <th className="text-left py-2 px-3 font-medium">添加日期</th>
                  <th className="text-right py-2 px-3 font-medium">成交量</th>
                  <th className="text-center py-2 px-3 font-medium w-16">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-light">
                {watchlist.map((item: any, i: number) => {
                  const isUp = (item.change_pct ?? 0) >= 0
                  const isSinceUp = (item.since_added_pct ?? 0) >= 0
                  return (
                    <tr key={i} className="hover:bg-bg-hover transition-all duration-200">
                      <td className="py-2.5 px-3 text-text-primary font-mono">{item.symbol}</td>
                      <td className="py-2.5 px-3 text-text-primary">{item.name || '-'}</td>
                      <td className="py-2.5 px-3 text-right text-text-primary">
                        {item.price != null ? Number(item.price).toFixed(2) : '-'}
                      </td>
                      <td className={cn('py-2.5 px-3 text-right font-medium', isUp ? 'text-rise' : 'text-fall')}>
                        {isUp ? '+' : ''}{item.change != null ? Number(item.change).toFixed(2) : '-'}
                      </td>
                      <td className={cn('py-2.5 px-3 text-right font-medium', isUp ? 'text-rise' : 'text-fall')}>
                        {isUp ? '+' : ''}{item.change_pct != null ? Number(item.change_pct).toFixed(2) : '-'}%
                      </td>
                      <td className="py-2.5 px-3 text-right text-text-secondary">
                        {item.added_price != null ? Number(item.added_price).toFixed(2) : '-'}
                      </td>
                      <td className={cn('py-2.5 px-3 text-right font-medium', isSinceUp ? 'text-rise' : 'text-fall')}>
                        {item.since_added_pct != null ? (
                          <>
                            {isSinceUp ? '+' : ''}{Number(item.since_added_pct).toFixed(2)}%
                          </>
                        ) : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-text-tertiary text-xs">
                        {item.added_at ? new Date(item.added_at).toLocaleDateString('zh-CN') : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-right text-text-secondary">
                        {item.volume != null ? Number(item.volume).toLocaleString() : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <button
                          onClick={() => handleDeleteWatchlist(item.symbol)}
                          className="text-text-tertiary hover:text-danger transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-text-tertiary text-sm">
            暂无自选股票，输入代码添加
          </div>
        )}
      </section>

      {/* 龙虎榜 */}
      <section className="mt-6 bg-bg-card border border-border rounded-xl p-4 card-hover">
        <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Swords className="w-5 h-5 text-accent" />
          龙虎榜
          {longhu?.date && (
            <span className="text-xs text-text-tertiary font-normal">{longhu.date}</span>
          )}
        </h2>
        {longhu?.data?.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-light text-text-tertiary">
                  <th className="text-left py-2 px-3 font-medium">代码</th>
                  <th className="text-left py-2 px-3 font-medium">名称</th>
                  <th className="text-right py-2 px-3 font-medium">收盘价</th>
                  <th className="text-right py-2 px-3 font-medium">涨跌幅</th>
                  <th className="text-left py-2 px-3 font-medium">上榜原因</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-light">
                {longhu.data.map((item: any, i: number) => {
                  const isUp = (item.change_pct ?? 0) >= 0
                  return (
                    <tr key={i} className="hover:bg-bg-hover transition-all duration-200">
                      <td className="py-2.5 px-3 text-text-primary font-mono">{item.symbol}</td>
                      <td className="py-2.5 px-3 text-text-primary">{item.name}</td>
                      <td className="py-2.5 px-3 text-right text-text-primary">{item.close_price?.toFixed ? item.close_price.toFixed(2) : item.close_price}</td>
                      <td className={cn('py-2.5 px-3 text-right font-medium', isUp ? 'text-rise' : 'text-fall')}>
                        {isUp ? '+' : ''}{item.change_pct?.toFixed ? item.change_pct.toFixed(2) : item.change_pct}%
                      </td>
                      <td className="py-2.5 px-3 text-text-secondary max-w-xs">
                        {Array.isArray(item.reason) ? (
                          <div className="flex flex-wrap gap-1">
                            {item.reason.map((r: string, ri: number) => (
                              <span key={ri} className="inline-block px-1.5 py-0.5 rounded bg-bg-secondary text-xs text-text-secondary whitespace-nowrap">
                                {r}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="truncate block" title={item.reason}>{item.reason}</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-text-tertiary text-sm">暂无龙虎榜数据</div>
        )}
      </section>
    </div>
  )
}

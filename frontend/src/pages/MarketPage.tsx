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
} from 'lucide-react'
import { marketApi } from '@/lib/api'
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
          <TrendingUp className="w-4 h-4 text-success" />
        ) : (
          <TrendingDown className="w-4 h-4 text-danger" />
        )}
      </div>
      <div className="text-2xl font-bold text-text-primary mb-1">
        {formatNumber(index.value)}
      </div>
      <div className={cn('text-sm font-medium', isUp ? 'text-success' : 'text-danger')}>
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
      <span className={cn('text-sm font-medium', isUp ? 'text-success' : 'text-danger')}>
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
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [dataSource, setDataSource] = useState<'live' | 'demo' | 'unknown'>('unknown')
  const [lastUpdated, setLastUpdated] = useState('')
  const [error, setError] = useState('')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async (isBackground = false) => {
    if (!isBackground) setLoading(true)
    else setRefreshing(true)
    setError('')

    try {
      const [indicesRes, sectorsRes, northboundRes] = await Promise.all([
        marketApi.getIndices(),
        marketApi.getSectors(),
        marketApi.getNorthbound().catch(() => ({ data: null })),
      ])

      const idxData = indicesRes.data || {}
      const secData = sectorsRes.data || {}

      setIndices(idxData.indices || [])
      setSectors(secData.sectors || [])
      setNorthbound(northboundRes.data)

      // 只要任一接口是 demo，就标记为 demo
      const isDemo = idxData.source === 'demo' || secData.source === 'demo'
      setDataSource(isDemo ? 'demo' : 'live')
      setLastUpdated(idxData.timestamp || new Date().toISOString())
    } catch (err: any) {
      setError(err.message || '获取数据失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchData()

    intervalRef.current = setInterval(() => {
      fetchData(true)
    }, REFRESH_INTERVAL)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchData])

  if (loading && !refreshing) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="animate-shimmer w-8 h-8 rounded-full" />
      </div>
    )
  }

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
                      item.net_inflow >= 0 ? 'text-success' : 'text-danger'
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
    </div>
  )
}

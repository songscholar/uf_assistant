import { useState, useEffect, useCallback, useRef } from 'react'
import { Bitcoin, TrendingUp, TrendingDown, RefreshCw, AlertTriangle, Clock } from 'lucide-react'
import { cryptoApi } from '@/lib/api'
import type { CryptoPrice } from '@/types'
import { cn, formatNumber } from '@/lib/utils'

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

export default function CryptoPage() {
  const [cryptos, setCryptos] = useState<CryptoPrice[]>([])
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
      const res = await cryptoApi.getTop(20)
      const data = res.data || {}

      setCryptos(data.cryptos || [])
      setDataSource(data.source === 'demo' ? 'demo' : 'live')
      setLastUpdated(new Date().toISOString())
    } catch (err: any) {
      setError(err.message || '获取数据失败')
      setCryptos([])
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
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Bitcoin className="w-5 h-5 text-accent" />
            加密货币行情
          </h2>
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
            当前展示的是模拟数据，非真实行情。数据源服务暂时不可用（可能是网络问题）。
            系统每 30 秒会自动重试获取真实数据。
          </div>
        </div>
      )}

      <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg-secondary text-text-secondary text-xs">
              <th className="text-left px-4 py-2">排名</th>
              <th className="text-left px-4 py-2">币种</th>
              <th className="text-right px-4 py-2">价格 (USDT)</th>
              <th className="text-right px-4 py-2">24h涨跌</th>
              <th className="text-right px-4 py-2">24h成交额</th>
              <th className="text-right px-4 py-2">市值</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">
            {cryptos.length > 0 ? (
              cryptos.map((crypto, index) => {
                const isUp = (crypto.change_pct_24h || 0) >= 0
                return (
                  <tr key={crypto.symbol} className="hover:bg-bg-hover transition-smooth">
                    <td className="px-4 py-3 text-text-tertiary">{index + 1}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-accent-bg flex items-center justify-center">
                          <Bitcoin className="w-4 h-4 text-accent" />
                        </div>
                        <span className="font-medium text-text-primary">
                          {crypto.symbol.replace('/USDT', '')}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-text-primary font-medium">
                      ${formatNumber(crypto.price)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={cn(
                          'flex items-center justify-end gap-1 font-medium',
                          isUp ? 'text-success' : 'text-danger'
                        )}
                      >
                        {isUp ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                        {isUp ? '+' : ''}
                        {(crypto.change_pct_24h || 0).toFixed(2)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-text-secondary">
                      ${crypto.quote_volume_24h ? (crypto.quote_volume_24h / 1e9).toFixed(2) : '--'}B
                    </td>
                    <td className="px-4 py-3 text-right text-text-secondary">--</td>
                  </tr>
                )
              })
            ) : (
              <tr>
                <td colSpan={6} className="text-center py-8 text-text-tertiary text-sm">
                  暂无加密货币数据
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

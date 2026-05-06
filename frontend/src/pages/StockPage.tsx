import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Search, TrendingUp, TrendingDown } from 'lucide-react'
import { stockApi } from '@/lib/api'
import type { StockRealtime, KlineData, StockInfo } from '@/types'
import { cn, formatNumber, formatPercent } from '@/lib/utils'

export default function StockPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const [searchSymbol, setSearchSymbol] = useState(symbol || '')
  const [stockInfo, setStockInfo] = useState<StockInfo | null>(null)
  const [realtime, setRealtime] = useState<StockRealtime | null>(null)
  const [history, setHistory] = useState<KlineData[]>([])
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('daily')

  useEffect(() => {
    if (!symbol) return
    const fetchData = async () => {
      try {
        const [infoRes, realtimeRes, historyRes] = await Promise.all([
          stockApi.getInfo(symbol),
          stockApi.getRealtime(symbol),
          stockApi.getHistory(symbol, period),
        ])
        setStockInfo(infoRes.data)
        setRealtime(realtimeRes.data)
        setHistory(historyRes.data || [])
      } catch (err) {
        // Demo data
        setStockInfo({ symbol, name: '贵州茅台', industry: '白酒', market: '沪市' })
        setRealtime({
          symbol,
          name: '贵州茅台',
          current_price: 1688.0,
          change: 20.5,
          change_percent: 1.23,
          open: 1670,
          high: 1695,
          low: 1665,
          prev_close: 1667.5,
          volume: 25432,
          amount: 428000000,
        })
      }
    }
    fetchData()
  }, [symbol, period])

  const handleSearch = () => {
    if (searchSymbol) {
      window.location.href = `/stock/${searchSymbol}`
    }
  }

  const isUp = (realtime?.change || 0) >= 0

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Search */}
      <div className="flex gap-2 mb-6">
        <div className="flex-1 relative">
          <input
            type="text"
            value={searchSymbol}
            onChange={(e) => setSearchSymbol(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="输入股票代码或名称..."
            className="w-full px-4 py-2.5 pl-10 rounded-xl bg-bg-card border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
          />
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
        </div>
        <button
          onClick={handleSearch}
          className="px-4 py-2.5 rounded-xl bg-accent text-white text-sm font-medium hover:bg-accent-light transition-smooth"
        >
          搜索
        </button>
      </div>

      {realtime && (
        <>
          {/* Price Header */}
          <div className="bg-bg-card border border-border rounded-xl p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h1 className="text-xl font-bold text-text-primary">{realtime.name}</h1>
                <span className="text-sm text-text-tertiary">{realtime.symbol}</span>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-text-primary">
                  ¥{formatNumber(realtime.current_price)}
                </div>
                <div className={cn('text-sm font-medium flex items-center justify-end gap-1', isUp ? 'text-success' : 'text-danger')}>
                  {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  {isUp ? '+' : ''}{formatNumber(realtime.change)} ({formatPercent(realtime.change_percent)})
                </div>
              </div>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-4 text-sm">
              <div>
                <div className="text-text-tertiary text-xs">今开</div>
                <div className="text-text-primary font-medium">{formatNumber(realtime.open)}</div>
              </div>
              <div>
                <div className="text-text-tertiary text-xs">最高</div>
                <div className="text-text-primary font-medium">{formatNumber(realtime.high)}</div>
              </div>
              <div>
                <div className="text-text-tertiary text-xs">最低</div>
                <div className="text-text-primary font-medium">{formatNumber(realtime.low)}</div>
              </div>
              <div>
                <div className="text-text-tertiary text-xs">昨收</div>
                <div className="text-text-primary font-medium">{formatNumber(realtime.prev_close)}</div>
              </div>
              <div>
                <div className="text-text-tertiary text-xs">成交量</div>
                <div className="text-text-primary font-medium">{realtime.volume.toLocaleString()}手</div>
              </div>
              <div>
                <div className="text-text-tertiary text-xs">成交额</div>
                <div className="text-text-primary font-medium">{(realtime.amount / 1e8).toFixed(2)}亿</div>
              </div>
            </div>
          </div>

          {/* Period Tabs */}
          <div className="flex gap-2 mb-4">
            {(['daily', 'weekly', 'monthly'] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-smooth',
                  period === p
                    ? 'bg-accent text-white'
                    : 'bg-bg-card border border-border text-text-secondary hover:bg-bg-hover'
                )}
              >
                {p === 'daily' ? '日K' : p === 'weekly' ? '周K' : '月K'}
              </button>
            ))}
          </div>

          {/* Chart Placeholder */}
          <div className="bg-bg-card border border-border rounded-xl p-4 mb-4 h-80 flex items-center justify-center">
            <div className="text-center text-text-tertiary">
              <TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>K 线图区域</p>
              <p className="text-xs mt-1">({period === 'daily' ? '日K' : period === 'weekly' ? '周K' : '月K'}数据)</p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Search, TrendingUp, TrendingDown, FileText } from 'lucide-react'
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

  // Financial data
  const [activeTab, setActiveTab] = useState<'chart' | 'financial'>('chart')
  const [financial, setFinancial] = useState<any>(null)
  const [financialLoading, setFinancialLoading] = useState(false)

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

  // Fetch financial data when tab switches to financial
  useEffect(() => {
    if (!symbol || activeTab !== 'financial') return
    const fetchFinancial = async () => {
      setFinancialLoading(true)
      try {
        const res = await stockApi.getFinancial(symbol)
        setFinancial(res.data)
      } catch (err) {
        // Demo data
        setFinancial({
          symbol,
          profit: [
            { date: '2024-09-30', revenue: 1207.76, net_profit: 608.28 },
            { date: '2024-06-30', revenue: 819.31, net_profit: 416.96 },
            { date: '2024-03-31', revenue: 464.85, net_profit: 240.65 },
            { date: '2023-12-31', revenue: 1505.60, net_profit: 747.34 },
          ],
        })
      } finally {
        setFinancialLoading(false)
      }
    }
    fetchFinancial()
  }, [symbol, activeTab])

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

          {/* Tabs: Chart / Financial */}
          <div className="flex items-center gap-1 mb-4 border-b border-border">
            {[
              { key: 'chart' as const, label: '行情', icon: TrendingUp },
              { key: 'financial' as const, label: '财务', icon: FileText },
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

          {activeTab === 'chart' && (
            <>
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

          {activeTab === 'financial' && (
            <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
              {financialLoading ? (
                <div className="h-40 flex items-center justify-center">
                  <div className="animate-shimmer w-8 h-8 rounded-full" />
                </div>
              ) : financial?.profit?.length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-bg-secondary text-text-secondary text-xs">
                      <th className="text-left px-4 py-2 font-medium">报告期</th>
                      <th className="text-right px-4 py-2 font-medium">营业收入 (亿元)</th>
                      <th className="text-right px-4 py-2 font-medium">净利润 (亿元)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-light">
                    {financial.profit.map((item: any, i: number) => (
                      <tr key={i} className="hover:bg-bg-hover transition-colors duration-150">
                        <td className="px-4 py-3 text-text-primary">{item.date}</td>
                        <td className="px-4 py-3 text-right text-text-primary">{item.revenue?.toFixed(2)}</td>
                        <td className="px-4 py-3 text-right text-text-primary">{item.net_profit?.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-center py-8 text-text-tertiary text-sm">暂无财务数据</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

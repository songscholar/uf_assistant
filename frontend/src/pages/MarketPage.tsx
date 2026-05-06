import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Activity, Flame, ArrowUpRight } from 'lucide-react'
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
        <span className="text-sm font-medium text-text-secondary">{index.name}</span>
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

export default function MarketPage() {
  const [indices, setIndices] = useState<MarketIndex[]>([])
  const [sectors, setSectors] = useState<SectorData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [indicesRes, sectorsRes] = await Promise.all([
          marketApi.getIndices(),
          marketApi.getSectors(),
        ])
        setIndices(indicesRes.data || [])
        setSectors(sectorsRes.data || [])
      } catch (err) {
        setIndices([
          { name: '上证指数', symbol: 'SH000001', value: 3456.78, change: 12.45, change_percent: 0.36 },
          { name: '深证成指', symbol: 'SZ399001', value: 11234.56, change: -15.32, change_percent: -0.14 },
          { name: '创业板指', symbol: 'SZ399006', value: 2345.67, change: 28.9, change_percent: 1.23 },
          { name: '科创50', symbol: 'SH000688', value: 1234.56, change: -8.23, change_percent: -0.67 },
        ])
        setSectors([
          { name: '半导体', change_percent: 3.45 },
          { name: '新能源', change_percent: 2.87 },
          { name: '人工智能', change_percent: 2.34 },
          { name: '医药生物', change_percent: 1.89 },
          { name: '消费电子', change_percent: 1.56 },
          { name: '汽车整车', change_percent: -0.78 },
          { name: '银行', change_percent: -0.45 },
          { name: '房地产', change_percent: -1.23 },
        ])
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="animate-shimmer w-8 h-8 rounded-full" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <section className="mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Activity className="w-5 h-5 text-accent" />
          大盘指数
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {indices.map((index) => (
            <IndexCard key={index.symbol} index={index} />
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="bg-bg-card border border-border rounded-xl p-4 card-hover">
          <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Flame className="w-5 h-5 text-accent" />
            板块热点
          </h2>
          <div className="divide-y divide-border-light">
            {sectors.map((sector, i) => (
              <SectorRow key={sector.name} sector={sector} rank={i + 1} />
            ))}
          </div>
        </section>

        <section className="bg-bg-card border border-border rounded-xl p-4 card-hover">
          <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
            <ArrowUpRight className="w-5 h-5 text-accent" />
            北向资金
          </h2>
          <div className="text-center py-8">
            <div className="text-3xl font-bold text-success mb-2">+28.45 亿</div>
            <div className="text-sm text-text-secondary">今日净流入</div>
            <div className="mt-4 flex items-center justify-center gap-4 text-sm">
              <div>
                <div className="text-text-tertiary">沪股通</div>
                <div className="font-medium text-success">+15.23亿</div>
              </div>
              <div className="w-px h-8 bg-border" />
              <div>
                <div className="text-text-tertiary">深股通</div>
                <div className="font-medium text-success">+13.22亿</div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { Bitcoin, TrendingUp, TrendingDown } from 'lucide-react'
import { cryptoApi } from '@/lib/api'
import type { CryptoPrice } from '@/types'
import { cn, formatNumber } from '@/lib/utils'

export default function CryptoPage() {
  const [cryptos, setCryptos] = useState<CryptoPrice[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await cryptoApi.getTop(20)
        setCryptos(res.data || [])
      } catch (err) {
        setCryptos([
          { symbol: 'BTC/USDT', price: 87456.32, change_24h: 1234.56, change_24h_percent: 1.43, volume_24h: 32500000000, market_cap: 1720000000000 },
          { symbol: 'ETH/USDT', price: 3456.78, change_24h: -45.23, change_24h_percent: -1.29, volume_24h: 15000000000, market_cap: 415000000000 },
          { symbol: 'SOL/USDT', price: 178.45, change_24h: 8.92, change_24h_percent: 5.26, volume_24h: 3200000000, market_cap: 82000000000 },
          { symbol: 'XRP/USDT', price: 2.34, change_24h: 0.05, change_24h_percent: 2.18, volume_24h: 1800000000, market_cap: 135000000000 },
          { symbol: 'DOGE/USDT', price: 0.34, change_24h: -0.01, change_24h_percent: -2.86, volume_24h: 1200000000, market_cap: 50000000000 },
        ])
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  return (
    <div className="h-full overflow-y-auto p-4">
      <section className="mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Bitcoin className="w-5 h-5 text-accent" />
          加密货币行情
        </h2>

        {loading ? (
          <div className="animate-shimmer h-40 rounded-xl" />
        ) : (
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
                {cryptos.map((crypto, index) => {
                  const isUp = crypto.change_24h_percent >= 0
                  return (
                    <tr key={crypto.symbol} className="hover:bg-bg-hover transition-smooth">
                      <td className="px-4 py-3 text-text-tertiary">{index + 1}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 rounded-full bg-accent-bg flex items-center justify-center">
                            <Bitcoin className="w-4 h-4 text-accent" />
                          </div>
                          <span className="font-medium text-text-primary">{crypto.symbol.replace('/USDT', '')}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-text-primary font-medium">
                        ${formatNumber(crypto.price)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={cn('flex items-center justify-end gap-1 font-medium', isUp ? 'text-success' : 'text-danger')}>
                          {isUp ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                          {isUp ? '+' : ''}{crypto.change_24h_percent.toFixed(2)}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-text-secondary">
                        ${(crypto.volume_24h / 1e9).toFixed(2)}B
                      </td>
                      <td className="px-4 py-3 text-right text-text-secondary">
                        ${(crypto.market_cap / 1e9).toFixed(2)}B
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

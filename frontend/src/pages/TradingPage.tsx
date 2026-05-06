import { useState, useEffect } from 'react'
import { Wallet, ArrowUpDown, ListOrdered, Package } from 'lucide-react'
import { tradingApi } from '@/lib/api'
import type { Order, Position, Portfolio } from '@/types'
import { cn, formatNumber, formatPercent } from '@/lib/utils'

export default function TradingPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [activeTab, setActiveTab] = useState<'order' | 'positions' | 'orders'>('order')

  // Order form state
  const [orderSymbol, setOrderSymbol] = useState('')
  const [orderSide, setOrderSide] = useState<'buy' | 'sell'>('buy')
  const [orderPrice, setOrderPrice] = useState('')
  const [orderQuantity, setOrderQuantity] = useState('')

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [portfolioRes, positionsRes, ordersRes] = await Promise.all([
          tradingApi.getPortfolio(),
          tradingApi.getPositions(),
          tradingApi.getOrders(),
        ])
        setPortfolio(portfolioRes.data)
        setPositions(positionsRes.data || [])
        setOrders(ordersRes.data || [])
      } catch (err) {
        // Demo data
        setPortfolio({
          total_assets: 1000000,
          available_cash: 653000,
          position_value: 347000,
          total_pnl: 125000,
          total_pnl_percent: 12.5,
        })
        setPositions([
          { symbol: '600519', name: '贵州茅台', quantity: 100, avg_cost: 1600, current_price: 1688, market_value: 168800, pnl: 8800, pnl_percent: 5.5 },
          { symbol: '002594', name: '比亚迪', quantity: 200, avg_cost: 240, current_price: 235, market_value: 47000, pnl: -1000, pnl_percent: -2.08 },
          { symbol: '300750', name: '宁德时代', quantity: 150, avg_cost: 180, current_price: 210, market_value: 31500, pnl: 4500, pnl_percent: 8.33 },
        ])
        setOrders([
          { order_id: '1', symbol: '600519', side: 'buy', quantity: 100, price: 1600, order_type: 'limit', status: 'filled', created_at: '2026-05-05T10:00:00Z' },
          { order_id: '2', symbol: '002594', side: 'buy', quantity: 200, price: 240, order_type: 'limit', status: 'filled', created_at: '2026-05-04T14:30:00Z' },
        ])
      }
    }
    fetchData()
  }, [])

  const handleSubmitOrder = async () => {
    if (!orderSymbol || !orderQuantity) return
    try {
      await tradingApi.submitOrder({
        symbol: orderSymbol,
        side: orderSide,
        quantity: parseFloat(orderQuantity),
        price: orderPrice ? parseFloat(orderPrice) : undefined,
        order_type: orderPrice ? 'limit' : 'market',
      })
      setOrderSymbol('')
      setOrderPrice('')
      setOrderQuantity('')
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Portfolio Overview */}
      {portfolio && (
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">总资产</div>
            <div className="text-xl font-bold text-text-primary">¥{formatNumber(portfolio.total_assets)}</div>
          </div>
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">可用资金</div>
            <div className="text-xl font-bold text-text-primary">¥{formatNumber(portfolio.available_cash)}</div>
          </div>
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">持仓市值</div>
            <div className="text-xl font-bold text-text-primary">¥{formatNumber(portfolio.position_value)}</div>
          </div>
          <div className="bg-bg-card border border-border rounded-xl p-4">
            <div className="text-xs text-text-tertiary mb-1">累计收益</div>
            <div className={cn('text-xl font-bold', portfolio.total_pnl >= 0 ? 'text-success' : 'text-danger')}>
              {portfolio.total_pnl >= 0 ? '+' : ''}{formatPercent(portfolio.total_pnl_percent)}
            </div>
          </div>
        </section>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-4 border-b border-border">
        {[
          { key: 'order' as const, label: '下单', icon: ArrowUpDown },
          { key: 'positions' as const, label: '持仓', icon: Package },
          { key: 'orders' as const, label: '订单', icon: ListOrdered },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-smooth',
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

      {/* Order Form */}
      {activeTab === 'order' && (
        <div className="bg-bg-card border border-border rounded-xl p-4 max-w-md">
          <div className="space-y-4">
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">股票代码</label>
              <input
                type="text"
                value={orderSymbol}
                onChange={(e) => setOrderSymbol(e.target.value)}
                placeholder="如: 600519"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">买卖方向</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setOrderSide('buy')}
                  className={cn(
                    'flex-1 py-2 rounded-lg text-sm font-medium transition-smooth',
                    orderSide === 'buy'
                      ? 'bg-success text-white'
                      : 'bg-bg-secondary text-text-secondary hover:bg-bg-hover'
                  )}
                >
                  买入
                </button>
                <button
                  onClick={() => setOrderSide('sell')}
                  className={cn(
                    'flex-1 py-2 rounded-lg text-sm font-medium transition-smooth',
                    orderSide === 'sell'
                      ? 'bg-danger text-white'
                      : 'bg-bg-secondary text-text-secondary hover:bg-bg-hover'
                  )}
                >
                  卖出
                </button>
              </div>
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">价格 (留空为市价)</label>
              <input
                type="number"
                value={orderPrice}
                onChange={(e) => setOrderPrice(e.target.value)}
                placeholder="市价"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">数量</label>
              <input
                type="number"
                value={orderQuantity}
                onChange={(e) => setOrderQuantity(e.target.value)}
                placeholder="100"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
              />
            </div>
            <button
              onClick={handleSubmitOrder}
              className={cn(
                'w-full py-2.5 rounded-lg text-sm font-medium transition-smooth',
                orderSide === 'buy'
                  ? 'bg-success text-white hover:bg-success/90'
                  : 'bg-danger text-white hover:bg-danger/90'
              )}
            >
              确认{orderSide === 'buy' ? '买入' : '卖出'}
            </button>
          </div>
        </div>
      )}

      {/* Positions Table */}
      {activeTab === 'positions' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                <th className="text-left px-4 py-2">代码</th>
                <th className="text-left px-4 py-2">名称</th>
                <th className="text-right px-4 py-2">数量</th>
                <th className="text-right px-4 py-2">成本</th>
                <th className="text-right px-4 py-2">现价</th>
                <th className="text-right px-4 py-2">市值</th>
                <th className="text-right px-4 py-2">盈亏</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {positions.map((pos) => (
                <tr key={pos.symbol} className="hover:bg-bg-hover transition-smooth">
                  <td className="px-4 py-3 text-text-primary font-medium">{pos.symbol}</td>
                  <td className="px-4 py-3 text-text-secondary">{pos.name}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{pos.quantity}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{formatNumber(pos.avg_cost)}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{formatNumber(pos.current_price)}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{formatNumber(pos.market_value)}</td>
                  <td className={cn('px-4 py-3 text-right font-medium', pos.pnl >= 0 ? 'text-success' : 'text-danger')}>
                    {pos.pnl >= 0 ? '+' : ''}{formatPercent(pos.pnl_percent)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Orders Table */}
      {activeTab === 'orders' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                <th className="text-left px-4 py-2">时间</th>
                <th className="text-left px-4 py-2">代码</th>
                <th className="text-left px-4 py-2">方向</th>
                <th className="text-right px-4 py-2">价格</th>
                <th className="text-right px-4 py-2">数量</th>
                <th className="text-left px-4 py-2">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {orders.map((order) => (
                <tr key={order.order_id} className="hover:bg-bg-hover transition-smooth">
                  <td className="px-4 py-3 text-text-secondary text-xs">
                    {new Date(order.created_at).toLocaleString('zh-CN')}
                  </td>
                  <td className="px-4 py-3 text-text-primary font-medium">{order.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      order.side === 'buy' ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                    )}>
                      {order.side === 'buy' ? '买入' : '卖出'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-text-primary">
                    {order.price ? formatNumber(order.price) : '市价'}
                  </td>
                  <td className="px-4 py-3 text-right text-text-primary">{order.quantity}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-text-secondary">{order.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

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
      {portfolio && (
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          {[
            { label: '总资产', value: `¥${formatNumber(portfolio.total_assets)}` },
            { label: '可用资金', value: `¥${formatNumber(portfolio.available_cash)}` },
            { label: '持仓市值', value: `¥${formatNumber(portfolio.position_value)}` },
            { label: '累计收益', value: `${portfolio.total_pnl >= 0 ? '+' : ''}${formatPercent(portfolio.total_pnl_percent)}`, color: portfolio.total_pnl >= 0 ? 'text-success' : 'text-danger' },
          ].map((item) => (
            <div
              key={item.label}
              className="bg-bg-card border border-border rounded-xl p-4 card-hover cursor-pointer"
            >
              <div className="text-xs text-text-tertiary mb-1">{item.label}</div>
              <div className={cn('text-xl font-bold', item.color || 'text-text-primary')}>{item.value}</div>
            </div>
          ))}
        </section>
      )}

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

      {activeTab === 'order' && (
        <div className="bg-bg-card border border-border rounded-xl p-4 max-w-md card-hover">
          <div className="space-y-4">
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">股票代码</label>
              <input
                type="text"
                value={orderSymbol}
                onChange={(e) => setOrderSymbol(e.target.value)}
                placeholder="如: 600519"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
              />
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">买卖方向</label>
              <div className="flex gap-2">
                {(['buy', 'sell'] as const).map((side) => (
                  <button
                    key={side}
                    onClick={() => setOrderSide(side)}
                    className={cn(
                      'flex-1 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                      orderSide === side
                        ? side === 'buy' ? 'bg-[rgba(74,222,128,0.15)] text-[#4ade80]' : 'bg-[rgba(248,113,113,0.15)] text-[#f87171]'
                        : 'bg-bg-secondary text-text-secondary hover:bg-bg-hover'
                    )}
                  >
                    {side === 'buy' ? '买入' : '卖出'}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">价格 (留空为市价)</label>
              <input
                type="number"
                value={orderPrice}
                onChange={(e) => setOrderPrice(e.target.value)}
                placeholder="市价"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
              />
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">数量</label>
              <input
                type="number"
                value={orderQuantity}
                onChange={(e) => setOrderQuantity(e.target.value)}
                placeholder="100"
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
              />
            </div>
            <button
              onClick={handleSubmitOrder}
              className={cn(
                'w-full py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                orderSide === 'buy'
                  ? 'bg-[rgba(74,222,128,0.15)] text-[#4ade80] hover:bg-[rgba(74,222,128,0.25)] hover:-translate-y-[1px] hover:shadow-md active:translate-y-0'
                  : 'bg-[rgba(248,113,113,0.15)] text-[#f87171] hover:bg-[rgba(248,113,113,0.25)] hover:-translate-y-[1px] hover:shadow-md active:translate-y-0'
              )}
            >
              确认{orderSide === 'buy' ? '买入' : '卖出'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'positions' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                {['代码', '名称', '数量', '成本', '现价', '市值', '盈亏'].map((h) => (
                  <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {positions.map((pos) => (
                <tr
                  key={pos.symbol}
                  className="hover:bg-bg-hover transition-colors duration-150 cursor-pointer"
                >
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

      {activeTab === 'orders' && (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-secondary text-text-secondary text-xs">
                {['时间', '代码', '方向', '价格', '数量', '状态'].map((h) => (
                  <th key={h} className="text-left px-4 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {orders.map((order) => (
                <tr
                  key={order.order_id}
                  className="hover:bg-bg-hover transition-colors duration-150"
                >
                  <td className="px-4 py-3 text-text-secondary text-xs">{new Date(order.created_at).toLocaleString('zh-CN')}</td>
                  <td className="px-4 py-3 text-text-primary font-medium">{order.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      order.side === 'buy' ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                    )}>
                      {order.side === 'buy' ? '买入' : '卖出'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-text-primary">{order.price ? formatNumber(order.price) : '市价'}</td>
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

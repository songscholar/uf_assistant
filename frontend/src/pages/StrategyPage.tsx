import { useState, useEffect } from 'react'
import { Brain, Play, Search, Plus } from 'lucide-react'
import { strategyApi } from '@/lib/api'
import type { StrategyInfo, StrategySignal } from '@/types'
import { cn } from '@/lib/utils'

function StrategyCard({ strategy, onEvaluate }: { strategy: StrategyInfo; onEvaluate: () => void }) {
  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 hover:shadow-md transition-smooth">
      <div className="flex items-start justify-between mb-2">
        <div className="w-10 h-10 rounded-lg bg-accent-bg flex items-center justify-center">
          <Brain className="w-5 h-5 text-accent" />
        </div>
        <button
          onClick={onEvaluate}
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-light transition-smooth flex items-center gap-1"
        >
          <Play className="w-3.5 h-3.5" />
          运行
        </button>
      </div>
      <h3 className="font-semibold text-text-primary mb-1">{strategy.name}</h3>
      <p className="text-sm text-text-secondary">{strategy.description}</p>
    </div>
  )
}

export default function StrategyPage() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [symbol, setSymbol] = useState('600519')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ strategy: string; signal: StrategySignal } | null>(null)

  useEffect(() => {
    strategyApi.list().then((res) => {
      setStrategies(res.data?.strategies || [
        { key: 'ma_crossover', name: '均线交叉', description: '基于短期与长期移动平均线的交叉信号' },
        { key: 'macd', name: 'MACD', description: '基于MACD指标的金叉死叉信号' },
        { key: 'rsi', name: 'RSI', description: '基于相对强弱指标的超买超卖信号' },
        { key: 'bollinger', name: '布林带', description: '基于布林带上下轨的突破信号' },
      ])
    })
  }, [])

  const handleEvaluate = async (key: string) => {
    setLoading(true)
    try {
      const res = await strategyApi.evaluate(key, symbol)
      setResult({ strategy: key, signal: res.data?.signal || null })
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Strategy Grid */}
      <section className="mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-3">策略库</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {strategies.map((strategy) => (
            <StrategyCard
              key={strategy.key}
              strategy={strategy}
              onEvaluate={() => handleEvaluate(strategy.key)}
            />
          ))}
        </div>
      </section>

      {/* Stock Screener */}
      <section className="bg-bg-card border border-border rounded-xl p-4 mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
          <Search className="w-5 h-5 text-accent" />
          选股器
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">股票代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="如: 600519"
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">最低价格</label>
            <input
              type="number"
              placeholder="0"
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">最高价格</label>
            <input
              type="number"
              placeholder="不限"
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary mb-1 block">最小涨跌幅(%)</label>
            <input
              type="number"
              placeholder="-10"
              className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
            />
          </div>
        </div>
        <button className="px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-light transition-smooth flex items-center gap-2">
          <Search className="w-4 h-4" />
          开始选股
        </button>
      </section>

      {/* Result */}
      {result && (
        <section className="bg-bg-card border border-border rounded-xl p-4">
          <h3 className="font-semibold text-text-primary mb-2">策略分析结果</h3>
          <div className="flex items-center gap-4">
            <div
              className={cn(
                'px-3 py-1.5 rounded-lg text-sm font-medium',
                result.signal?.direction === 'buy' && 'bg-success-bg text-success',
                result.signal?.direction === 'sell' && 'bg-danger-bg text-danger',
                result.signal?.direction === 'hold' && 'bg-bg-secondary text-text-secondary'
              )}
            >
              {result.signal?.direction === 'buy' && '买入信号'}
              {result.signal?.direction === 'sell' && '卖出信号'}
              {result.signal?.direction === 'hold' && '观望'}
              {!result.signal?.direction && '无信号'}
            </div>
            {result.signal?.confidence && (
              <div className="text-sm text-text-secondary">
                置信度: {(result.signal.confidence * 100).toFixed(1)}%
              </div>
            )}
          </div>
          {result.signal?.reason && (
            <p className="text-sm text-text-secondary mt-2">{result.signal.reason}</p>
          )}
        </section>
      )}
    </div>
  )
}

import { useState, useEffect } from 'react'
import { Brain, Play, Search, ArrowRight } from 'lucide-react'
import { strategyApi } from '@/lib/api'
import type { StrategyInfo, StrategySignal } from '@/types'
import { cn } from '@/lib/utils'

function StrategyCard({ strategy, onEvaluate }: { strategy: StrategyInfo; onEvaluate: () => void }) {
  return (
    <div
      className={cn(
        'bg-bg-card border border-border rounded-xl p-4',
        'card-hover cursor-pointer relative overflow-hidden'
      )}
    >
      <div className="absolute top-0 left-0 right-0 h-[2px] bg-accent transform scale-x-0 origin-left transition-transform duration-500 group-hover:scale-x-100" />
      <div className="flex items-start justify-between mb-2">
        <div className="w-10 h-10 rounded-lg bg-accent-bg flex items-center justify-center">
          <Brain className="w-5 h-5 text-accent" />
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onEvaluate() }}
          className={cn(
            'px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200',
            'bg-accent text-white hover:bg-accent-light',
            'hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.985]',
            'flex items-center gap-1 shadow-sm hover:shadow-md'
          )}
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

      <section className="bg-bg-card border border-border rounded-xl p-4 mb-6 card-hover">
        <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
          <Search className="w-5 h-5 text-accent" />
          选股器
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          {[
            { label: '股票代码', val: symbol, set: setSymbol, placeholder: '如: 600519' },
            { label: '最低价格', val: '', placeholder: '0' },
            { label: '最高价格', val: '', placeholder: '不限' },
            { label: '最小涨跌幅(%)', val: '', placeholder: '-10' },
          ].map((f, i) => (
            <div key={i}>
              <label className="text-xs text-text-tertiary mb-1 block">{f.label}</label>
              <input
                type={i === 0 ? 'text' : 'number'}
                value={f.val}
                onChange={(e) => i === 0 && f.set ? f.set(e.target.value) : null}
                placeholder={f.placeholder}
                className="w-full px-3 py-2 rounded-lg bg-bg-secondary border border-border text-text-primary text-sm transition-all duration-200 hover:border-border-focus focus:border-accent"
              />
            </div>
          ))}
        </div>
        <button className={cn(
          'px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium',
          'flex items-center gap-2 shadow-sm',
          'transition-all duration-200 hover:bg-accent-light hover:-translate-y-[1px] hover:shadow-md',
          'active:translate-y-0 active:scale-[0.985]'
        )}>
          <Search className="w-4 h-4" />
          开始选股
        </button>
      </section>

      {result && (
        <section className="bg-bg-card border border-border rounded-xl p-4 card-hover animate-fade-in-up">
          <h3 className="font-semibold text-text-primary mb-2">策略分析结果</h3>
          <div className="flex items-center gap-4">
            <div className={cn(
              'px-3 py-1.5 rounded-lg text-sm font-medium',
              result.signal?.direction === 'buy' && 'bg-success-bg text-success',
              result.signal?.direction === 'sell' && 'bg-danger-bg text-danger',
              result.signal?.direction === 'hold' && 'bg-bg-secondary text-text-secondary'
            )}>
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

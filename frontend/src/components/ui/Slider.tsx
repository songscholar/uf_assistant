import { cn } from '@/lib/utils'

interface SliderProps {
  value: number
  min: number
  max: number
  step?: number
  label: string
  valueFormatter?: (value: number) => string
  onChange: (value: number) => void
}

export default function Slider({
  value,
  min,
  max,
  step = 0.01,
  label,
  valueFormatter = (v) => v.toFixed(2),
  onChange,
}: SliderProps) {
  const percentage = ((value - min) / (max - min)) * 100

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-[13px] font-medium text-text-secondary">{label}</span>
        <span className="text-[12px] font-mono font-medium text-text-tertiary bg-bg-hover px-2 py-0.5 rounded-md min-w-[52px] text-right">
          {valueFormatter(value)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="relative flex-1 h-[5px]">
          {/* Track background */}
          <div className="absolute inset-0 rounded-full bg-border" />
          {/* Track fill */}
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-accent transition-all duration-75"
            style={{ width: `${percentage}%` }}
          />
          {/* Native range input (invisible but functional) */}
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />
          {/* Custom thumb */}
          <div
            className="absolute top-1/2 -translate-y-1/2 w-[18px] h-[18px] rounded-full bg-accent border-[3px] border-bg-card shadow-md pointer-events-none transition-all duration-75 hover:scale-110"
            style={{ left: `calc(${percentage}% - 9px)` }}
          />
        </div>
      </div>
    </div>
  )
}

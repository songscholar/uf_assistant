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
    <div className="mb-5">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-[13px] font-medium text-text-secondary">{label}</span>
        <span className="text-[12px] font-mono font-medium text-text-tertiary bg-bg-hover/80 px-2.5 py-0.5 rounded-md min-w-[52px] text-right">
          {valueFormatter(value)}
        </span>
      </div>
      <div className="relative h-5 flex items-center">
        {/* Track background */}
        <div className="absolute left-0 right-0 h-[5px] rounded-full bg-border overflow-hidden">
          {/* Track fill */}
          <div
            className="h-full rounded-full bg-accent transition-all duration-75"
            style={{ width: `${percentage}%` }}
          />
        </div>
        {/* Native range input */}
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
        />
        {/* Custom thumb - follows percentage */}
        <div
          className={cn(
            'absolute w-[18px] h-[18px] rounded-full pointer-events-none',
            'bg-accent border-[3px] border-bg-card shadow-md',
            'transition-transform duration-150',
            'hover:scale-125'
          )}
          style={{ left: `calc(${percentage}% - 9px)` }}
        />
      </div>
    </div>
  )
}

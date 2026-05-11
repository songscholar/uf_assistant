import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatNumber(num: number, decimals = 2): string {
  if (num === null || num === undefined) return '--'
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function formatPercent(num: number): string {
  if (num === null || num === undefined) return '--'
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(2)}%`
}

export function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

/**
 * 格式化成交量/成交额
 * 新浪接口成交量单位是"手"（1手=100股），成交额单位是"元"
 */
export function formatVolume(value: number | null | undefined, type: 'volume' | 'amount' = 'volume'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  const num = Number(value)
  if (type === 'amount') {
    if (num >= 1e8) return `${(num / 1e8).toFixed(2)}亿`
    if (num >= 1e4) return `${(num / 1e4).toFixed(2)}万`
    return num.toLocaleString('zh-CN')
  }
  // volume (手)
  if (num >= 1e8) return `${(num / 1e8).toFixed(2)}亿手`
  if (num >= 1e4) return `${(num / 1e4).toFixed(2)}万手`
  return `${num.toLocaleString('zh-CN')}手`
}

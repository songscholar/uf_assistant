import { describe, it, expect } from 'vitest'
import { cn, formatNumber, formatPercent, formatDate, formatTime } from '../utils'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('deduplicates tailwind classes', () => {
    expect(cn('px-4 px-8')).toBe('px-8')
  })

  it('handles conditional classes', () => {
    expect(cn('base', false && 'hidden', 'active')).toBe('base active')
  })

  it('handles empty input', () => {
    expect(cn()).toBe('')
  })
})

describe('formatNumber', () => {
  it('formats integers with default decimals', () => {
    const result = formatNumber(1234)
    expect(result).toContain('1,234')
  })

  it('formats with custom decimals', () => {
    const result = formatNumber(1234.5678, 2)
    expect(result).toContain('1,234.57')
  })

  it('formats zero', () => {
    expect(formatNumber(0)).toContain('0')
  })
})

describe('formatPercent', () => {
  it('formats positive with + sign', () => {
    expect(formatPercent(12.345)).toBe('+12.35%')
  })

  it('formats zero', () => {
    expect(formatPercent(0)).toBe('0.00%')
  })

  it('formats negative', () => {
    expect(formatPercent(-5.67)).toBe('-5.67%')
  })
})

describe('formatDate', () => {
  it('formats a valid date string', () => {
    const result = formatDate('2026-05-08T12:00:00')
    expect(result).toBeTruthy()
    expect(typeof result).toBe('string')
  })
})

describe('formatTime', () => {
  it('returns relative time for recent dates', () => {
    const now = new Date()
    const recent = new Date(now.getTime() - 30000) // 30 seconds ago
    const result = formatTime(recent.toISOString())
    expect(result).toBe('刚刚')
  })

  it('returns minutes ago', () => {
    const now = new Date()
    const recent = new Date(now.getTime() - 5 * 60000) // 5 minutes ago
    const result = formatTime(recent.toISOString())
    expect(result).toBe('5分钟前')
  })
})

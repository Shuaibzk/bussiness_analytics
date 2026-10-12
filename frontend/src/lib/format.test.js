import { describe, expect, it } from 'vitest'
import { cx, dimLabel, fmt, monthName } from './format'

describe('fmt', () => {
  it('formats currency with compact notation for large values', () => {
    expect(fmt('currency', 1234.5)).toBe('$1,235')
    expect(fmt('currency', 12.5)).toBe('$12.5')
    expect(fmt('currency', 3_845_611, { short: true })).toBe('$3.8M')
    expect(fmt('currency', 25_000)).toBe('$25K')
  })
  it('keeps the sign on negative money', () => {
    expect(fmt('currency', -60_000, { short: true })).toBe('-$60K')
    expect(fmt('currency', -12.5)).toBe('-$12.5')
  })
  it('formats percents, fractions, days and counts', () => {
    expect(fmt('percent', 18.567)).toBe('18.6%')
    expect(fmt('percent_frac', 0.25)).toBe('25%')
    expect(fmt('days', 11.44)).toBe('11.4 d')
    expect(fmt('number', 7235)).toBe('7,235')
  })
  it('renders missing values as a dash', () => {
    expect(fmt('currency', null)).toBe('-')
    expect(fmt('percent', undefined)).toBe('-')
    expect(fmt('number', Number.NaN)).toBe('-')
  })
})

describe('dimLabel', () => {
  it('labels discount, month and month-of-year dimensions', () => {
    expect(dimLabel('discount', 0.3)).toBe('30%')
    expect(dimLabel('month_of_year', 3)).toBe('Mar')
    expect(dimLabel('month', '2023-11')).toBe('Nov 23')
    expect(dimLabel('region', 'Asia')).toBe('Asia')
    expect(dimLabel('region', null)).toBe('-')
  })
})

describe('helpers', () => {
  it('cx joins truthy class names', () => {
    expect(cx('a', false, 'b', null, undefined, 'c')).toBe('a b c')
  })
  it('monthName is 1-based', () => {
    expect(monthName(1)).toBe('Jan')
    expect(monthName(12)).toBe('Dec')
  })
})

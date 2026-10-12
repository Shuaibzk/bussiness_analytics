const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const compact = (v) =>
  v == null ? '-' : new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(v)

export function fmt(kind, v, { short = false } = {}) {
  if (v == null || Number.isNaN(v)) return '-'
  switch (kind) {
    case 'currency': {
      const sign = v < 0 ? '-' : ''
      const a = Math.abs(v)
      return short || a >= 10000 ? `${sign}$${compact(a)}` : `${sign}$${a.toLocaleString('en-US', { maximumFractionDigits: a < 1000 ? 2 : 0 })}`
    }
    case 'percent':
      return `${v.toFixed(1)}%`
    case 'percent_frac':
      return `${Math.round(v * 100)}%`
    case 'days':
      return `${v.toFixed(1)} d`
    case 'number':
      return Math.abs(v) >= 100000 && short ? compact(v) : Math.round(v).toLocaleString('en-US')
    default:
      return String(v)
  }
}

export function dimLabel(dim, v) {
  if (v == null) return '-'
  if (dim === 'discount') return `${Math.round(Number(v) * 100)}%`
  if (dim === 'month_of_year') return MONTHS[Number(v) - 1]
  if (dim === 'month' && typeof v === 'string') {
    const [y, m] = v.split('-')
    return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`
  }
  return String(v)
}

export const monthName = (m) => MONTHS[m - 1]
export const cx = (...a) => a.filter(Boolean).join(' ')

export const PALETTE = ['#5ee1ff', '#7c9cff', '#a78bfa', '#e879f9', '#34d399', '#fbbf24', '#fb7185', '#60a5fa']

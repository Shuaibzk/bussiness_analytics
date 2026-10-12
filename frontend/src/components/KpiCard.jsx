import { Area, AreaChart, ResponsiveContainer } from 'recharts'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Card } from './ui'
import { cx, fmt } from '../lib/format'

export default function KpiCard({ card, delay, color = '#7c8cff' }) {
  const d = card.delta
  const change = d ? (d.pct ?? d.abs) : null
  const goodUp = card.good_direction === 'up'
  const positive = change != null && (goodUp ? change >= 0 : change <= 0)
  const spark = (card.spark || []).map((v, i) => ({ i, v }))
  const id = `sp-${card.key}`
  return (
    <Card delay={delay} className="relative overflow-hidden p-4">
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-[var(--body-muted)]">{card.label}</span>
        {change != null && (
          <span className={cx('inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-medium',
            positive ? 'bg-emerald-400/10 text-emerald-300' : 'bg-rose-400/10 text-rose-300')}>
            {change >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {Math.abs(change)}{d.pct != null ? '%' : ' pp'}
          </span>
        )}
      </div>
      <div className="mt-2 text-[28px] font-medium leading-none tracking-tight text-white">
        {fmt(card.fmt, card.value, { short: true })}
      </div>
      <div className="mt-3 h-10 -mx-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={spark} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.8} fill={`url(#${id})`} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

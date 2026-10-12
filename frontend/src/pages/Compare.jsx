import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, Trophy } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAsync, useFilters } from '../lib/filters'
import { PALETTE, dimLabel, fmt, monthName } from '../lib/format'
import { PageHeader } from '../components/Layout'
import FilterBar, { ActiveChips } from '../components/FilterBar'
import { Card, CardHeader, ErrorBox, Skeleton } from '../components/ui'
import { TrendChart } from '../components/charts'

const COMPARE_DIMS = ['year', 'region', 'country', 'category', 'sub_category', 'segment', 'shipping_method', 'payment_method', 'gender', 'status']
const LOWER_IS_BETTER = new Set(['return_rate', 'cancel_rate', 'avg_shipping_days', 'avg_shipping_cost', 'shipping_cost', 'loss_rate', 'returned_revenue', 'cancelled_revenue'])
const WANT = ['revenue', 'profit', 'margin', 'orders', 'aov', 'units', 'return_rate', 'cancel_rate', 'loss_rate', 'avg_shipping_days', 'avg_shipping_cost']

export default function Compare() {
  const { meta } = useAuth()
  const { filters, basis } = useFilters()
  const dims = meta.options.dims
  const available = COMPARE_DIMS.filter((d) => dims[d] && dims[d].values.length >= 2)
  const [dim, setDim] = useState(available.includes('region') ? 'region' : available[0])
  const values = dims[dim]?.values || []
  const [a, setA] = useState(String(values[0]))
  const [b, setB] = useState(String(values[1]))
  useEffect(() => { setA(String(values[0])); setB(String(values[1])) }, [dim]) // eslint-disable-line react-hooks/exhaustive-deps

  const metrics = WANT.filter((k) => meta.metrics.some((m) => m.key === k))
  const info = Object.fromEntries(meta.metrics.map((m) => [m.key, m]))
  const f = { ...filters, [dim]: [dim === 'year' ? Number(a) : a, dim === 'year' ? Number(b) : b] }
  const cmp = useAsync(() => api.query({ metrics, group_by: [dim], filters: f, basis }), [dim, a, b, basis, JSON.stringify(filters)])
  const first = metrics.includes('revenue') ? 'revenue' : 'orders'
  const trend = useAsync(() => api.query({ metrics: [first], group_by: ['month', dim], filters: f, basis }), [dim, a, b, basis, first, JSON.stringify(filters)])

  const rowFor = (v) => {
    if (!cmp.data) return null
    const i = cmp.data.rows.findIndex((r) => String(r[0]) === String(v))
    if (i < 0) return null
    return Object.fromEntries(cmp.data.columns.map((c, j) => [c.key, cmp.data.rows[i][j]]))
  }
  const A = rowFor(a), B = rowFor(b)

  const trendData = useMemo(() => {
    if (!trend.data) return []
    const map = {}
    trend.data.rows.forEach(([m, d, v]) => { (map[m] ||= { x: m })[String(d) === String(a) ? 'a' : 'b'] = v })
    return Object.values(map).sort((p, q) => (p.x < q.x ? -1 : 1))
  }, [trend.data, a, b])

  if (available.length === 0) return <div className="p-10 text-[var(--body-muted)]">Not enough distinct values within your access to compare.</div>
  const sel = 'rounded-lg border border-white/10 bg-[#0e1120] px-3 py-2 text-sm outline-none focus:border-white/40'
  let wins = { a: 0, b: 0 }
  const rows = metrics.map((k) => {
    if (!A || !B) return { k }
    const va = A[k], vb = B[k]
    const pct = va ? ((vb - va) / Math.abs(va)) * 100 : null
    const better = va === vb ? null : (vb > va) !== LOWER_IS_BETTER.has(k) ? 'a' : 'b'
    if (better) wins[better]++
    return { k, va, vb, pct, better }
  })

  return (
    <div className="pb-10">
      <PageHeader title="Compare" subtitle="Put any two regions, categories, years, segments or shipping methods side by side." />
      <div className="sticky top-0 z-20 border-b border-white/[0.06] bg-[rgba(4,5,12,0.5)] px-5 sm:px-10 py-3 backdrop-blur-xl">
        <FilterBar show={['year', 'region', 'category', 'segment'].filter((k) => k !== dim)} />
        <div className="mt-2 empty:hidden"><ActiveChips /></div>
      </div>
      <div className="space-y-4 px-5 sm:px-10 pt-5">
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs uppercase tracking-wider text-[var(--body-muted)]">Compare by</span>
            <select value={dim} onChange={(e) => setDim(e.target.value)} className={sel}>
              {available.map((d) => <option key={d} value={d}>{dims[d].label}</option>)}
            </select>
            <select value={a} onChange={(e) => setA(e.target.value)} className={`${sel} !border-cyan-300/50`}>{values.map((v) => <option key={v}>{String(v)}</option>)}</select>
            <ArrowRight size={16} className="text-[var(--body-muted)]/70" />
            <select value={b} onChange={(e) => setB(e.target.value)} className={`${sel} !border-cyan-400/40`}>{values.map((v) => <option key={v}>{String(v)}</option>)}</select>
            {A && B && <span className="ml-auto flex items-center gap-1.5 text-xs text-[var(--body-muted)]"><Trophy size={13} className="text-amber-300" /> {a} leads {wins.a} metrics - {b} leads {wins.b}</span>}
          </div>
        </Card>

        {cmp.error && <ErrorBox error={cmp.error} />}
        <div className="grid gap-4 xl:grid-cols-5">
          <Card className="xl:col-span-3">
            <CardHeader title="Head-to-head" subtitle={`${dims[dim].label}: ${a} vs ${b}`} />
            <div className="p-2 pb-3">
              {!cmp.data ? <div className="p-3"><Skeleton className="h-72" /></div> : (
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
                    <th className="px-4 py-2 font-medium">Metric</th>
                    <th className="px-4 py-2 text-right font-medium text-cyan-200">{a}</th>
                    <th className="px-4 py-2 text-right font-medium text-cyan-300">{b}</th>
                    <th className="px-4 py-2 text-right font-medium">Change</th></tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.k} className="border-t border-white/[0.05]">
                        <td className="px-4 py-2.5 text-[var(--body-muted)]">{info[r.k].label}</td>
                        <td className={`px-4 py-2.5 text-right tabular-nums ${r.better === 'a' ? 'font-medium text-white' : 'text-[var(--body-muted)]'}`}>{fmt(info[r.k].fmt, r.va)}</td>
                        <td className={`px-4 py-2.5 text-right tabular-nums ${r.better === 'b' ? 'font-medium text-white' : 'text-[var(--body-muted)]'}`}>{fmt(info[r.k].fmt, r.vb)}</td>
                        <td className={`px-4 py-2.5 text-right tabular-nums text-xs ${r.pct == null ? 'text-[var(--body-muted)]/70' : (r.better === 'b') ? 'text-emerald-300' : 'text-rose-300'}`}>
                          {r.pct == null ? '-' : `${r.pct >= 0 ? '+' : ''}${r.pct.toFixed(1)}%`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>
          <Card className="xl:col-span-2">
            <CardHeader title={`${info[first].label} trend`} subtitle="Monthly, both selections overlaid" />
            <div className="p-3 pt-4">
              <TrendChart data={trendData} kind="line" height={300} xFmt={(v) => dimLabel('month', v)}
                series={[{ key: 'a', name: a, fmt: info[first].fmt, color: PALETTE[0] }, { key: 'b', name: b, fmt: info[first].fmt, color: PALETTE[1] }]} />
            </div>
          </Card>
        </div>
        <p className="text-center text-[11px] text-[var(--body-muted)]/70">Green change = {b} is better than {a} (lower is better for returns, cancellations, cost and delivery time). {monthName(1) && ''}</p>
      </div>
    </div>
  )
}

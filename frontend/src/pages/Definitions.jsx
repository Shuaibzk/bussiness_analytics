import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAsync } from '../lib/filters'
import { dimLabel, fmt } from '../lib/format'
import { recs } from '../lib/query'
import { PageHeader } from '../components/Layout'
import { Badge, Card, CardHeader, Skeleton } from '../components/ui'

const RULES = [
  ['Revenue', 'Unit price x quantity x (1 - discount). Verified on every one of the 10,000 orders when the data is loaded.'],
  ['Profit', 'Revenue minus product cost. Shipping cost is tracked separately and is not part of profit.'],
  ['Profit margin', 'Profit divided by revenue (of the same set of orders).'],
  ['Net vs gross', 'NET excludes orders with status Returned or Cancelled - they are not realised sales. GROSS includes every order. The dashboards default to net; switch with the Net / Gross toggle.'],
  ['Return / cancellation rate', 'Returned (or cancelled) orders divided by ALL orders. These two rates ignore the net/gross toggle.'],
  ['"Orders" in the AI chat', 'Questions like "how many orders" count orders placed (gross) unless you ask for net or delivered orders.'],
  ['Loss-making order', 'An order whose profit is below zero.'],
  ['Slow / fast delivery', 'Slow = more than 15 days from order to delivery. Fast = 7 days or less.'],
  ['Repeat customer', 'A customer with two or more orders in the selected period and scope.'],
  ['Customer segment / gender', 'Recorded on each order and not stable per customer (about 41% of customers appear with more than one segment), so segment analysis describes orders rather than a fixed customer property.'],
]

const plural = (s) => (s.endsWith('y') ? s.slice(0, -1) + 'ies' : s + 's')

export default function Definitions() {
  const { meta, user } = useAuth()
  const money = meta.metrics.some((m) => m.key === 'revenue')
  const [min, max] = meta.options.date_range
  const months = useAsync(() => api.query({ metrics: ['orders'], group_by: ['month'], basis: 'gross' }), [])
  const net = useAsync(() => (money ? Promise.all([api.query({ metrics: ['revenue', 'orders'], basis: 'net' }), api.query({ metrics: ['gross_revenue', 'orders'], basis: 'gross' })]) : Promise.resolve(null)), [])
  const last12 = recs(months.data).slice(-12)
  const peak = Math.max(1, ...recs(months.data).map((r) => r.orders))
  const tail = last12.length && last12[last12.length - 1].orders < 0.25 * peak

  return (
    <div className="pb-10">
      <PageHeader title="Data & definitions" subtitle="How every number in this app is calculated, what the data covers, and what you are allowed to see." />
      <div className="space-y-4 px-5 pt-3 sm:px-10">
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader title="Calculation rules" subtitle="Applied identically on every page, in exports and in the AI analyst" />
            <dl className="space-y-3 px-6 pb-5 pt-4">
              {RULES.filter(([k]) => money || !['Revenue', 'Profit', 'Profit margin', 'Loss-making order'].includes(k)).map(([k, v]) => (
                <div key={k} className="grid gap-1 sm:grid-cols-[11rem_1fr]"><dt className="text-[0.9rem] font-medium text-[var(--heading)]">{k}</dt><dd className="text-[0.88rem] leading-relaxed text-[var(--body-muted)]">{v}</dd></div>))}
            </dl>
          </Card>
          <Card>
            <CardHeader title="Net vs gross, in numbers" subtitle="Whole dataset within your access" />
            <div className="space-y-3 px-6 pb-5 pt-4 text-[0.9rem]">
              {money
                ? (net.data ? (() => {
                  const n = net.data[0].rows[0], g = net.data[1].rows[0]
                  return <>
                    <div className="flex justify-between"><span className="text-[var(--body-muted)]">Gross revenue (all orders)</span><span className="tabular-nums text-white">{fmt('currency', g[0])}</span></div>
                    <div className="flex justify-between"><span className="text-[var(--body-muted)]">Net revenue</span><span className="tabular-nums text-white">{fmt('currency', n[0])}</span></div>
                    <div className="hairline" />
                    <div className="flex justify-between"><span className="text-[var(--body-muted)]">Excluded (returned + cancelled)</span><span className="tabular-nums text-amber-200">{fmt('currency', g[0] - n[0])} ({((g[0] - n[0]) / g[0] * 100).toFixed(1)}%)</span></div>
                    <div className="flex justify-between"><span className="text-[var(--body-muted)]">Orders placed / net orders</span><span className="tabular-nums text-white">{fmt('number', g[1])} / {fmt('number', n[1])}</span></div>
                  </>
                })() : <Skeleton className="h-28" />)
                : <p className="text-[var(--body-muted)]">Financial figures are hidden for your role, so only order counts apply to you.</p>}
            </div>
          </Card>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <Card>
            <CardHeader title="What the data covers" />
            <ul className="space-y-2 px-6 pb-5 pt-4 text-[0.9rem] text-[var(--body-muted)]">
              <li>Period: <span className="text-white">{min}</span> to <span className="text-white">{max}</span></li>
              {Object.entries(meta.options.dims).filter(([k]) => ['region', 'country', 'category', 'sub_category', 'segment'].includes(k)).map(([k, v]) => (
                <li key={k}>{plural(v.label)} in scope: <span className="text-white">{v.values.length}</span></li>))}
              <li className="pt-1">Source: e-commerce order extract (one row per order). Loaded and validated: no missing values, no duplicate order ids, revenue and profit formulas reconcile on every row.</li>
            </ul>
          </Card>
          <Card className="xl:col-span-2">
            <CardHeader title="Known caveat: the latest months" subtitle="Orders placed per month, last 12 months of the data" />
            <div className="px-6 pb-5 pt-4">
              <div className="flex flex-wrap gap-2">
                {last12.map((r) => <Badge key={r.month}>{dimLabel('month', r.month)}: {fmt('number', r.orders)}</Badge>)}
              </div>
              <p className={`mt-4 flex gap-2 text-[0.88rem] ${tail ? 'text-amber-200' : 'text-emerald-300'}`}>
                {tail ? <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> : <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden="true" />}
                {tail
                  ? 'Order volume tapers off steadily to almost nothing by the end of the data. A smooth slide like this usually means an incomplete or late-loaded extract rather than a real collapse in demand - confirm the data cut-off before drawing conclusions about the most recent year. Year-over-year comparisons and forecasts flag this automatically.'
                  : 'No sign of an incomplete latest period.'}
              </p>
            </div>
          </Card>
        </div>

        <Card>
          <CardHeader title="Your access" subtitle={`${user.role_label}${user.scope ? ` - ${user.scope.value} only` : ''}`} />
          <div className="space-y-2 px-6 pb-5 pt-4 text-[0.9rem] text-[var(--body-muted)]">
            <p>{user.role_description}</p>
            <p>Hidden from you: {user.hidden_columns.length ? user.hidden_columns.map((c) => <Badge key={c} tone="bad" className="mr-1">{c}</Badge>) : <span className="text-white">nothing</span>}</p>
          </div>
        </Card>

        <Card>
          <CardHeader title="Metric glossary" subtitle="Everything you can measure" />
          <div className="grid gap-x-8 gap-y-3 px-6 pb-5 pt-4 md:grid-cols-2">
            {meta.metrics.map((m) => (
              <div key={m.key} className="flex items-start gap-3">
                <Badge className="mt-0.5 shrink-0">{m.fmt}</Badge>
                <div><div className="text-[0.9rem] text-[var(--heading)]">{m.label}</div><div className="text-[0.8rem] text-[var(--body-muted)]">{m.desc}</div></div>
              </div>))}
          </div>
        </Card>
      </div>
    </div>
  )
}

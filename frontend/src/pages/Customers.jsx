import { ShieldAlert } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAsync, useFilters } from '../lib/filters'
import { PALETTE, dimLabel, fmt } from '../lib/format'
import { Body, recs } from '../lib/query'
import { PageHeader } from '../components/Layout'
import FilterBar, { ActiveChips } from '../components/FilterBar'
import PrintHeader from '../components/PrintHeader'
import { CsvButton, PrintButton, RowsCsvButton } from '../components/tools'
import { Badge, Card, CardHeader, Skeleton } from '../components/ui'
import { ColBars, ComboChart, Donut } from '../components/charts'

function Stat({ label, value, sub, delay }) {
  return (
    <Card delay={delay} className="p-4">
      <div className="text-xs font-medium uppercase tracking-wider text-[var(--body-muted)]">{label}</div>
      <div className="mt-2 text-[1.9rem] font-medium leading-none tracking-tight text-white">{value}</div>
      {sub && <div className="mt-2 text-[0.75rem] text-[var(--body-muted)]">{sub}</div>}
    </Card>
  )
}

export default function Customers() {
  const { user } = useAuth()
  const { body } = useFilters()
  const state = useAsync(() => api.customers(body), [JSON.stringify(body)])
  const d = state.data
  const c = d?.customers
  const segKeys = d?.segments?.columns.map((x) => x.key) || []
  const money = segKeys.includes('revenue')

  return (
    <div className="pb-10">
      <PrintHeader title="Customer analytics" />
      <PageHeader title="Customers" subtitle="How customers buy: repeat behaviour, segments and who matters most."><PrintButton /></PageHeader>
      <div className="no-print sticky top-0 z-20 border-b border-white/[0.06] bg-[rgba(4,5,12,0.5)] px-5 py-3 backdrop-blur-xl sm:px-10">
        <FilterBar />
        <div className="mt-2 empty:hidden"><ActiveChips /></div>
      </div>

      <div className="space-y-4 px-5 pt-5 sm:px-10">
        {d && !d.customer_access && (
          <div className="glass flex items-start gap-3 rounded-2xl px-5 py-4 text-sm text-[var(--body-muted)]">
            <ShieldAlert size={18} className="mt-0.5 shrink-0 text-amber-300" aria-hidden="true" />
            <span>Customer identifiers are hidden for your role ({user.role_label}), so individual-customer analysis (repeat buying, top customers) is not available. You can still analyse customer <strong className="text-white">segments</strong> below.</span>
          </div>
        )}

        {c && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat delay={0} label="Unique customers" value={fmt('number', c.unique)} sub={`${fmt('number', c.repeat)} bought more than once`} />
              <Stat delay={0.05} label="Repeat rate" value={`${c.repeat_rate}%`} sub="Customers with 2+ orders" />
              <Stat delay={0.1} label="Orders per customer" value={c.orders_per_customer} sub={`Best customer: ${c.max_orders} orders`} />
              {c.concentration && <Stat delay={0.15} label="Top 1% of customers" value={`${c.concentration.top_1pct}%`} sub={`of net revenue (top 10%: ${c.concentration.top_10pct}%)`} />}
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <Card>
                <CardHeader title="How often do customers order?" subtitle="Customers by number of orders placed" />
                <div className="p-3 pt-4"><ColBars data={c.distribution.map((r) => ({ x: `${r.orders} order${r.orders === '1' ? '' : 's'}`, customers: r.customers }))} height={250}
                  series={[{ key: 'customers', name: 'Customers', fmt: 'number', color: PALETTE[0] }]} /></div>
              </Card>
              <Card>
                <CardHeader title="New vs returning customers" subtitle="Customers active each year, by whether they had ordered before" />
                <div className="p-3 pt-4"><ColBars data={c.new_vs_returning.map((r) => ({ x: String(r.year), new: r.new, returning: r.returning }))} height={250} stacked
                  series={[{ key: 'new', name: 'New', fmt: 'number', color: PALETTE[1] }, { key: 'returning', name: 'Returning', fmt: 'number', color: PALETTE[3] }]} /></div>
              </Card>
            </div>

            {c.top.length > 0 && (
              <Card className="overflow-hidden">
                <CardHeader title="Top 10 customers" subtitle="By net revenue within the current filters"
                  right={<RowsCsvButton name="top_customers" columns={['Customer', 'Segment', 'Orders', 'First order', 'Last order', 'Net revenue', 'Profit']}
                    rows={c.top.map((r) => [r.customer_id, r.segment, r.orders, r.first_order, r.last_order, r.revenue, r.profit])} />} />
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead><tr className="border-y border-white/[0.07] text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
                      {['Customer', 'Segment', 'Orders', 'First order', 'Last order', 'Net revenue', ...(c.top[0].profit !== undefined ? ['Profit'] : [])].map((h, i) => <th key={h} scope="col" className={`px-4 py-3 font-medium ${i >= 5 || i === 2 ? 'text-right' : ''}`}>{h}</th>)}</tr></thead>
                    <tbody>
                      {c.top.map((r) => (
                        <tr key={r.customer_id} className="border-b border-white/[0.04] hover:bg-white/[0.04]">
                          <td className="px-4 py-2 font-medium text-white">{r.customer_id}</td>
                          <td className="px-4 py-2"><Badge>{r.segment}</Badge></td>
                          <td className="px-4 py-2 text-right tabular-nums">{r.orders}</td>
                          <td className="px-4 py-2 text-[var(--body-muted)]">{r.first_order}</td>
                          <td className="px-4 py-2 text-[var(--body-muted)]">{r.last_order}</td>
                          <td className="px-4 py-2 text-right tabular-nums">{fmt('currency', r.revenue)}</td>
                          {r.profit !== undefined && <td className={`px-4 py-2 text-right tabular-nums ${r.profit < 0 ? 'text-rose-300' : ''}`}>{fmt('currency', r.profit)}</td>}
                        </tr>))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </>
        )}
        {state.loading && !d && <Skeleton className="h-64" />}

        {d?.segments && (
          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title="Customer segments" subtitle="Volume and value by segment" right={<CsvButton res={d.segments} name="customer_segments" />} />
              <div className="p-3 pt-4"><Body state={{ data: d.segments, loading: false }} h={250}>{(res) => {
                const [a, b] = money ? ['revenue', 'aov'] : ['orders', 'return_rate']
                return <ComboChart data={recs(res).map((r) => ({ x: r.segment, ...r }))} height={250}
                  bar={{ key: a, name: a === 'revenue' ? 'Net revenue' : 'Orders', fmt: a === 'revenue' ? 'currency' : 'number', color: PALETTE[2] }}
                  line={{ key: b, name: b === 'aov' ? 'Avg order value' : 'Return rate', fmt: b === 'aov' ? 'currency' : 'percent', color: PALETTE[0] }} />
              }}</Body></div>
              <div className="overflow-x-auto px-3 pb-4">
                <table className="w-full min-w-[520px] text-sm">
                  <thead><tr className="text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">{d.segments.columns.map((col) => <th key={col.key} scope="col" className={`px-3 py-2 font-medium ${col.role === 'metric' ? 'text-right' : ''}`}>{col.label}</th>)}</tr></thead>
                  <tbody>{d.segments.rows.map((r, i) => (
                    <tr key={i} className="border-t border-white/[0.05]">{r.map((v, j) => <td key={j} className={`px-3 py-2 ${d.segments.columns[j].role === 'metric' ? 'text-right tabular-nums' : 'text-white'}`}>{d.segments.columns[j].role === 'metric' ? fmt(d.segments.columns[j].fmt, v) : dimLabel(d.segments.columns[j].key, v)}</td>)}</tr>))}</tbody>
                </table>
              </div>
            </Card>
            {d.gender && (
              <Card>
                <CardHeader title="Gender split" subtitle="Share of orders" right={<CsvButton res={d.gender} name="gender_split" />} />
                <div className="p-5"><Donut height={180} fmtKind="number" data={recs(d.gender).map((r) => ({ name: r.gender, value: r.orders }))} /></div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Search } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { PALETTE, fmt } from '../lib/format'
import { Body, recs, useQuery } from '../lib/query'
import { PageHeader } from '../components/Layout'
import FilterBar, { ActiveChips } from '../components/FilterBar'
import PrintHeader from '../components/PrintHeader'
import { CsvButton, PrintButton, RowsCsvButton } from '../components/tools'
import { Card, CardHeader } from '../components/ui'
import { RankBars, TrendChart } from '../components/charts'

const ALL = ['orders', 'revenue', 'profit', 'margin', 'return_rate', 'avg_discount', 'loss_rate']

export default function Products() {
  const { meta } = useAuth()
  const keys = ALL.filter((k) => meta.metrics.some((m) => m.key === k))
  const info = Object.fromEntries(meta.metrics.map((m) => [m.key, m]))
  const money = keys.includes('revenue')
  const primary = money ? 'revenue' : 'orders'
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState(primary)
  const [desc, setDesc] = useState(true)

  const prod = useQuery({ metrics: keys, group_by: ['product', 'category'] })
  const sub = useQuery({ metrics: money ? ['revenue', 'profit'] : ['orders', 'return_rate'], group_by: ['sub_category'] })

  const rows = useMemo(() => recs(prod.data), [prod.data])
  const view = useMemo(() => {
    const q = search.trim().toLowerCase()
    const f = q ? rows.filter((r) => r.product.toLowerCase().includes(q) || r.category.toLowerCase().includes(q)) : rows
    return [...f].sort((a, b) => (sort === 'product' || sort === 'category' ? String(a[sort]).localeCompare(String(b[sort])) : (a[sort] ?? 0) - (b[sort] ?? 0)) * (desc ? -1 : 1))
  }, [rows, search, sort, desc])

  // Pareto: how concentrated is the business in a few products?
  const pareto = useMemo(() => {
    const ranked = [...rows].sort((a, b) => (b[primary] ?? 0) - (a[primary] ?? 0))
    const total = ranked.reduce((s, r) => s + (r[primary] || 0), 0) || 1
    let cum = 0
    const pts = ranked.map((r, i) => { cum += r[primary] || 0; return { x: i + 1, share: +(cum / total * 100).toFixed(1) } })
    const n80 = pts.findIndex((p) => p.share >= 80) + 1
    return { pts, n80, n: ranked.length }
  }, [rows, primary])

  const bars = (key, list) => list.map((r) => ({ name: r.product, value: r[key] }))
  const byProfit = useMemo(() => [...rows].sort((a, b) => (b.profit ?? 0) - (a.profit ?? 0)), [rows])
  const highReturn = useMemo(() => [...rows].filter((r) => r.orders >= 30).sort((a, b) => b.return_rate - a.return_rate).slice(0, 8), [rows])
  const toggle = (k) => { if (k === sort) setDesc(!desc); else { setSort(k); setDesc(true) } }
  const cols = [['product', 'Product', 'text'], ['category', 'Category', 'text'], ...keys.map((k) => [k, info[k].label, info[k].fmt])]

  return (
    <div className="pb-10">
      <PrintHeader title="Product performance" />
      <PageHeader title="Products" subtitle="Which products and sub-categories drive results - and which lose money or come back.">
        <PrintButton />
      </PageHeader>
      <div className="no-print sticky top-0 z-20 border-b border-white/[0.06] bg-[rgba(4,5,12,0.5)] px-5 py-3 backdrop-blur-xl sm:px-10">
        <FilterBar />
        <div className="mt-2 empty:hidden"><ActiveChips /></div>
      </div>

      <div className="space-y-4 px-5 pt-5 sm:px-10">
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-1">
            <CardHeader title="Sub-category performance" subtitle={money ? 'Net revenue by sub-category' : 'Orders by sub-category'} right={<CsvButton res={sub.data} name="sub_categories" />} />
            <div className="p-3 pt-2"><Body state={sub}>{(d) => <RankBars data={recs(d).map((r) => ({ name: r.sub_category, value: r[primary] }))} fmtKind={money ? 'currency' : 'number'} color={PALETTE[1]} height={Math.max(220, recs(d).length * 30 + 20)} />}</Body></div>
          </Card>
          <Card className="xl:col-span-2">
            <CardHeader title="Concentration (Pareto)" subtitle="Cumulative share of the total by number of products, best first" />
            <div className="px-6 pt-3 text-[0.9rem] text-[var(--body-muted)]">
              {pareto.n ? <><span className="text-[1.6rem] font-medium text-white">{pareto.n80}</span> of {pareto.n} products ({Math.round(pareto.n80 / pareto.n * 100)}%) generate 80% of {money ? 'net revenue' : 'orders'}.</> : ' '}
            </div>
            <div className="p-3"><Body state={prod} h={220}>{() => <TrendChart data={pareto.pts} series={[{ key: 'share', name: 'Cumulative share', fmt: 'percent', color: PALETTE[2] }]} height={220} xFmt={(v) => `#${v}`} />}</Body></div>
          </Card>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          {money && (
            <>
              <Card><CardHeader title="Most profitable" subtitle="Top 8 by profit" /><div className="p-3 pt-2"><Body state={prod}>{() => <RankBars data={bars('profit', byProfit.slice(0, 8))} fmtKind="currency" color="#34d399" />}</Body></div></Card>
              <Card><CardHeader title="Least profitable" subtitle="Bottom 8 by profit" /><div className="p-3 pt-2"><Body state={prod}>{() => <RankBars data={bars('profit', byProfit.slice(-8).reverse())} fmtKind="currency" color="#fb7185" />}</Body></div></Card>
            </>
          )}
          <Card><CardHeader title="Highest return rates" subtitle="Products with at least 30 orders" /><div className="p-3 pt-2"><Body state={prod}>{() => <RankBars data={bars('return_rate', highReturn)} fmtKind="percent" color="#fbbf24" />}</Body></div></Card>
        </div>

        <Card className="overflow-hidden">
          <CardHeader title="Product leaderboard" subtitle={`${view.length} of ${rows.length} products - click a column to sort`}
            right={<div className="flex items-center gap-2">
              <label className="glass flex items-center gap-2 rounded-full px-3 py-1.5 focus-within:border-white/40">
                <Search size={14} className="text-[var(--body-muted)]" aria-hidden="true" />
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search products" aria-label="Search products" className="w-36 bg-transparent text-xs outline-none" />
              </label>
              <RowsCsvButton name="product_leaderboard" columns={cols.map((c) => c[1])} rows={view.map((r) => cols.map((c) => r[c[0]]))} />
            </div>} />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead><tr className="border-y border-white/[0.07] text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
                {cols.map(([k, label, f]) => (
                  <th key={k} scope="col" aria-sort={sort === k ? (desc ? 'descending' : 'ascending') : 'none'} className={`px-4 py-3 font-medium ${f === 'text' ? '' : 'text-right'}`}>
                    <button onClick={() => toggle(k)} className="inline-flex items-center gap-1 hover:text-white">{label}{sort === k && (desc ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}</button>
                  </th>))}
              </tr></thead>
              <tbody>
                {view.map((r) => (
                  <tr key={r.product} className="border-b border-white/[0.04] hover:bg-white/[0.04]">
                    {cols.map(([k, , f], i) => (
                      <td key={k} className={`whitespace-nowrap px-4 py-2 ${f === 'text' ? (i === 0 ? 'font-medium text-white' : 'text-[var(--body-muted)]') : 'text-right tabular-nums'} ${k === 'profit' && r.profit < 0 ? 'text-rose-300' : ''}`}>
                        {f === 'text' ? r[k] : fmt(f, r[k])}
                      </td>))}
                  </tr>))}
                {!view.length && <tr><td colSpan={cols.length} className="p-8 text-center text-[var(--body-muted)]">No products match</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}

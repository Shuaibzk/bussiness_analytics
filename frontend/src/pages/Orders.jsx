import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, Search } from 'lucide-react'
import { api } from '../lib/api'
import { useAsync, useFilters } from '../lib/filters'
import { fmt } from '../lib/format'
import { PageHeader } from '../components/Layout'
import FilterBar, { ActiveChips } from '../components/FilterBar'
import { Badge, Card, ErrorBox, Skeleton, statusTone } from '../components/ui'
import { useAuth } from '../lib/auth'

export default function Orders() {
  const { user } = useAuth()
  const { filters } = useFilters()
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('order_date')
  const [desc, setDesc] = useState(true)
  const [page, setPage] = useState(1)
  const [exporting, setExporting] = useState(false)

  useEffect(() => { const t = setTimeout(() => { setQ(search); setPage(1) }, 300); return () => clearTimeout(t) }, [search])
  useEffect(() => setPage(1), [JSON.stringify(filters)])

  const body = { filters, search: q, sort, desc, page, page_size: 25 }
  const state = useAsync(() => api.orders(body), [JSON.stringify(body)])
  const d = state.data
  const pages = d ? Math.max(1, Math.ceil(d.total / d.page_size)) : 1

  const toggleSort = (k) => { if (k === sort) setDesc(!desc); else { setSort(k); setDesc(true) } }
  const cell = (c, v) => {
    if (c.key === 'order_status') return <Badge tone={statusTone[v]}>{v}</Badge>
    if (c.key === 'profit') return <span className={v < 0 ? 'text-rose-300' : 'text-[var(--heading)]'}>{fmt('currency', v)}</span>
    if (c.fmt === 'text') return v
    return fmt(c.fmt, v)
  }

  return (
    <div className="pb-10">
      <PageHeader title="Orders" subtitle={`Order-level records within your access${user.hidden_columns.length ? ` - ${user.hidden_columns.length} sensitive columns are hidden for your role` : ''}`}>
        {user.features.includes('export') && (
          <button onClick={async () => { setExporting(true); try { await api.exportOrders({ filters, search: q, sort, desc }) } finally { setExporting(false) } }}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm font-medium hover:bg-white/10">
            <Download size={15} /> {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
        )}
      </PageHeader>
      <div className="sticky top-0 z-20 border-b border-white/[0.06] bg-[rgba(4,5,12,0.5)] px-5 sm:px-10 py-3 backdrop-blur-xl">
        <FilterBar />
        <div className="mt-2 empty:hidden"><ActiveChips /></div>
      </div>

      <div className="space-y-3 px-5 sm:px-10 pt-5">
        <div className="glass flex max-w-md items-center gap-2.5 rounded-xl px-3.5 py-2.5 focus-within:border-white/40">
          <Search size={15} className="text-[var(--body-muted)]" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search order id, product or customer..."
            className="w-full bg-transparent text-sm outline-none placeholder:text-[var(--body-muted)]/70" />
        </div>
        {state.error && <ErrorBox error={state.error} />}
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead>
                <tr className="border-b border-white/[0.07] text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
                  {(d?.columns || []).map((c) => (
                    <th key={c.key} onClick={() => toggleSort(c.key)} className={`cursor-pointer select-none whitespace-nowrap px-4 py-3 font-medium hover:text-white ${['number', 'currency', 'percent_frac'].includes(c.fmt) ? 'text-right' : ''}`}>
                      <span className="inline-flex items-center gap-1">{c.label}{sort === c.key && (desc ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!d && Array.from({ length: 10 }).map((_, i) => <tr key={i}><td className="p-3" colSpan={12}><Skeleton className="h-6" /></td></tr>)}
                {d?.rows.map((r) => (
                  <tr key={r[0]} className="border-b border-white/[0.04] transition-colors hover:bg-white/[0.04]">
                    {r.map((v, i) => (
                      <td key={i} className={`whitespace-nowrap px-4 py-2.5 ${['number', 'currency', 'percent_frac'].includes(d.columns[i].fmt) ? 'text-right tabular-nums' : ''} ${i === 0 ? 'font-medium text-white' : 'text-[var(--body-muted)]'}`}>
                        {cell(d.columns[i], v)}
                      </td>
                    ))}
                  </tr>
                ))}
                {d && !d.rows.length && <tr><td colSpan={12} className="p-10 text-center text-[var(--body-muted)]/70">No orders match the current filters</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-white/[0.07] px-4 py-3 text-xs text-[var(--body-muted)]">
            <span>{d ? `${((page - 1) * d.page_size + 1).toLocaleString()}-${Math.min(page * d.page_size, d.total).toLocaleString()} of ${d.total.toLocaleString()} orders` : ' '}</span>
            <div className="flex items-center gap-2">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-lg border border-white/10 p-1.5 hover:bg-white/10 disabled:opacity-30"><ChevronLeft size={14} /></button>
              <span>Page {page} / {pages.toLocaleString()}</span>
              <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-lg border border-white/10 p-1.5 hover:bg-white/10 disabled:opacity-30"><ChevronRight size={14} /></button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}

import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, Info, Lightbulb, TrendingDown } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAsync, useFilters } from '../lib/filters'
import { PALETTE, dimLabel, monthName } from '../lib/format'
import { Body, recs, useQuery } from '../lib/query'
import { PageHeader } from '../components/Layout'
import FilterBar, { ActiveChips } from '../components/FilterBar'
import KpiCard from '../components/KpiCard'
import TargetsCard from '../components/TargetsCard'
import { CsvButton, PrintButton } from '../components/tools'
import PrintHeader from '../components/PrintHeader'
import { Card, CardHeader, Segmented, Skeleton } from '../components/ui'
import { ColBars, ComboChart, Donut, ForecastChart, Heatmap, RankBars, TrendChart } from '../components/charts'

const TONE = {
  bad: [TrendingDown, 'text-rose-300 bg-rose-400/10 border-rose-400/20'],
  warn: [AlertTriangle, 'text-amber-300 bg-amber-400/10 border-amber-400/20'],
  good: [CheckCircle2, 'text-emerald-300 bg-emerald-400/10 border-emerald-400/20'],
  neutral: [Info, 'text-sky-300 bg-sky-400/10 border-sky-400/20'],
}

function Insights() {
  const { body } = useFilters()
  const [all, setAll] = useState(false)
  const state = useAsync(() => api.insights(body), [JSON.stringify(body)])
  if (state.error) return null
  const list = state.data || Array.from({ length: 3 })
  const shown = all ? list : list.slice(0, 6)
  return (
    <section aria-label="Auto-generated insights">
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--body-muted)]">
          <Lightbulb size={14} className="text-amber-300" aria-hidden="true" /> Auto-generated insights
        </div>
        {list.length > 6 && (
          <button onClick={() => setAll(!all)} className="no-print flex items-center gap-1 text-xs text-[var(--body-muted)] hover:text-white" aria-expanded={all}>
            {all ? 'Show fewer' : `Show all ${list.length}`} <ChevronDown size={13} className={all ? 'rotate-180' : ''} aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {shown.map((ins, i) => {
          if (!ins) return <Skeleton key={i} className="h-24" />
          const [Icon, cls] = TONE[ins.tone] || TONE.neutral
          return (
            <Card key={i} delay={i * 0.05} className="p-4">
              <div className="flex gap-3">
                <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${cls}`}><Icon size={16} aria-hidden="true" /></div>
                <div className="min-w-0">
                  <div className="text-sm font-medium leading-snug text-white">{ins.title}</div>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--body-muted)]">{ins.text}</p>
                </div>
              </div>
            </Card>
          )
        })}
      </div>
    </section>
  )
}

export default function Dashboard() {
  const { meta, user } = useAuth()
  const { body, setFilter, filters } = useFilters()
  const has = (k) => meta.metrics.some((m) => m.key === k)
  const money = has('revenue')
  const primary = money ? 'revenue' : 'orders'
  const primaryFmt = money ? 'currency' : 'number'
  const primaryLabel = money ? 'Net revenue' : 'Orders'
  const dims = meta.options.dims
  const kp = useAsync(() => api.kpis(body), [JSON.stringify(body)])

  const [grain, setGrain] = useState('month')
  const [mode, setMode] = useState('timeline')
  const [baseline, setBaseline] = useState('auto')
  const [geo, setGeo] = useState('region')
  const [prodMetric, setProdMetric] = useState(primary)
  const [catView, setCatView] = useState('category')
  const delivGeo = dims.region?.values.length > 1 ? 'region' : 'country'

  const trendMetrics = money ? ['revenue', 'profit'] : ['orders']
  const trend = useQuery(mode === 'yoy' ? { metrics: [primary], group_by: ['month_of_year', 'year'] } : { metrics: trendMetrics, group_by: [mode === 'forecast' ? 'month' : grain] })
  const fc = useAsync(() => (mode === 'forecast' ? api.forecast({ metric: primary, filters: body.filters, basis: body.basis, horizon: 6, baseline }) : Promise.resolve(null)),
    [mode, primary, JSON.stringify(body), baseline])
  const geoQ = useQuery({ metrics: [primary], group_by: [geo] }, [geo])
  const catQ = useQuery({ metrics: [primary], group_by: [catView], limit: 10 }, [catView])
  const prodQ = useQuery({ metrics: [prodMetric], group_by: ['product'], limit: 10 })
  const segQ = useQuery({ metrics: money ? ['revenue', 'aov'] : ['orders', 'return_rate'], group_by: ['segment'] }, ['segment'])
  const shipQ = useQuery({ metrics: ['avg_shipping_days', 'avg_shipping_cost', 'orders'], group_by: ['shipping_method'] }, ['shipping_method'])
  const delivQ = useQuery({ metrics: ['avg_shipping_days', 'slow_rate'], group_by: [delivGeo] }, [delivGeo])
  const statusQ = useQuery({ metrics: ['orders'], group_by: ['status'] }, ['status'], 'gross') // status split needs all orders
  const payQ = useQuery({ metrics: ['orders'], group_by: ['payment_method'] })
  const discQ = useQuery({ metrics: ['loss_rate', 'margin'], group_by: ['discount'] })
  const heatQ = useQuery({ metrics: [primary], group_by: ['year', 'month_of_year'] }, ['year', 'quarter_of_year', 'season'])
  const retQ = useQuery({ metrics: ['return_rate', 'cancel_rate'], group_by: ['category'] }, ['category'])

  const trendData = useMemo(() => {
    if (!trend.data) return { rows: [], series: [] }
    const r = recs(trend.data)
    if (mode === 'timeline') {
      const x = grain
      return { rows: r.map((d) => ({ ...d, x: d[x] })), series: trendMetrics.map((k, i) => ({ key: k, name: k === 'revenue' ? 'Net revenue' : k === 'profit' ? 'Profit' : 'Orders', fmt: k === 'orders' ? 'number' : 'currency', color: PALETTE[i === 0 ? 0 : 2] })) }
    }
    const byMonth = {}
    r.forEach((d) => { (byMonth[d.month_of_year] ||= { x: d.month_of_year })[`y${d.year}`] = d[primary] })
    const years = [...new Set(r.map((d) => d.year))].sort()
    return { rows: Object.values(byMonth).sort((a, b) => a.x - b.x), series: years.map((y, i) => ({ key: `y${y}`, name: String(y), fmt: primaryFmt, color: PALETTE[i % PALETTE.length] })) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trend.data, mode, grain])

  const forecastRows = useMemo(() => {
    const d = fc.data
    if (!d?.available) return []
    const rows = d.history.map((h) => ({ x: h.month, actual: h.value }))
    const last = rows[rows.length - 1]
    last.forecast = last.actual // join the two lines
    d.forecast.forEach((f) => rows.push({ x: f.month, forecast: f.value, band: [f.low, f.high] }))
    return rows
  }, [fc.data])

  const xFmt = mode === 'yoy' ? (v) => monthName(v) : mode === 'forecast' ? (v) => dimLabel('month', v) : (v) => dimLabel(grain, v)
  const toBars = (res, key) => recs(res).map((d) => ({ name: dimLabel(Object.keys(d)[0], d[Object.keys(d)[0]]), value: d[key] }))
  const heatCells = (res) => recs(res).map((d) => ({ year: d.year, month: d.month_of_year, value: d[primary] }))
  const discRows = (res) => recs(res).map((d) => ({ x: d.discount, ...d }))
  const csvHead = (res, name) => <CsvButton res={res} name={name} />

  return (
    <div className="pb-10">
      <PrintHeader title="Performance report" />
      <PageHeader title="Performance dashboard"
        subtitle={user.scope ? `Showing ${user.scope.column.replace('_', ' ')} ${user.scope.value} - your authorised slice of the data` : 'Global view across all regions and categories'}>
        <PrintButton label="Export report (PDF)" />
      </PageHeader>
      <div className="no-print sticky top-0 z-20 -mt-px border-b border-white/[0.06] bg-[rgba(4,5,12,0.5)] px-5 py-3 backdrop-blur-xl sm:px-10">
        <FilterBar />
        <div className="mt-2 empty:hidden"><ActiveChips /></div>
      </div>
      <div className="print-only px-2 pb-2 text-xs"><ActiveChips /></div>

      <div className="space-y-5 px-5 pt-5 sm:px-10">
        {/* KPIs */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {kp.data
            ? kp.data.cards.map((c, i) => <KpiCard key={c.key} card={c} delay={i * 0.04} color={PALETTE[i % PALETTE.length]} />)
            : Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-[132px]" />)}
        </div>
        {kp.data?.compared_to && <div className="-mt-2 text-right text-[11px] text-[var(--body-muted)]/70">Change vs {kp.data.compared_to}</div>}

        <Insights />

        {/* trend + category */}
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader title={mode === 'yoy' ? `${primaryLabel} by month, year over year` : mode === 'forecast' ? `${primaryLabel}: history and 6-month outlook` : `${primaryLabel}${money ? ' & profit' : ''} over time`}
              subtitle={mode === 'forecast' ? 'Seasonal baseline projection - a planning aid, not a guarantee' : 'Click a legend item to focus. Use the filters above to slice.'}
              right={<div className="flex flex-wrap items-center justify-end gap-2">
                <Segmented label="Chart mode" value={mode} onChange={setMode} options={[{ value: 'timeline', label: 'Timeline' }, { value: 'yoy', label: 'Year over year' }, { value: 'forecast', label: 'Forecast' }]} />
                {mode === 'timeline' && <Segmented label="Time grain" value={grain} onChange={setGrain} options={[{ value: 'month', label: 'Monthly' }, { value: 'quarter', label: 'Quarterly' }, { value: 'year', label: 'Yearly' }]} />}
                {mode === 'forecast' && fc.data?.tail_months > 0 && <Segmented label="Forecast baseline" value={baseline} onChange={setBaseline} options={[{ value: 'auto', label: 'Stable baseline' }, { value: 'recent', label: 'Recent months' }]} />}
                {mode !== 'forecast' && csvHead(trend.data, 'trend')}
              </div>} />
            {mode === 'forecast' ? (
              <div className="p-3 pt-4">
                <Body state={fc} h={290}>{(d) => d?.available
                  ? <>
                    {d.warning && <p className="mx-3 mb-2 flex gap-2 rounded-xl border border-amber-400/25 bg-amber-400/5 px-3 py-2 text-[0.75rem] text-amber-200"><AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />{d.warning}</p>}
                    <ForecastChart rows={forecastRows} fmtKind={primaryFmt} xFmt={xFmt} />
                    <p className="mx-3 mt-1 text-[0.7rem] text-[var(--body-muted)]/80">Shaded band = likely range (±{d.band_pct}%). {d.method}</p>
                  </>
                  : <p className="p-6 text-sm text-[var(--body-muted)]">{d?.reason || 'No forecast available.'}</p>}</Body>
              </div>
            ) : (
              <div className="p-3 pt-4"><Body state={trend} h={290}>{() => <TrendChart data={trendData.rows} series={trendData.series} kind={mode === 'yoy' ? 'line' : 'area'} xFmt={xFmt} height={290} />}</Body></div>
            )}
          </Card>
          <Card>
            <CardHeader title={`${primaryLabel} mix`}
              right={<div className="flex items-center gap-2">
                <Segmented label="Mix level" value={catView} onChange={setCatView} options={[{ value: 'category', label: 'Category' }, ...(dims.sub_category?.values.length > 1 ? [{ value: 'sub_category', label: 'Sub' }] : [])]} />
                {csvHead(catQ.data, 'mix')}
              </div>} />
            <div className="p-5"><Body state={catQ} h={240}>{(d) => <Donut data={toBars(d, primary)} fmtKind={primaryFmt} onPick={(n) => setFilter(catView, [n])} activeNames={filters[catView] || []} />}</Body></div>
          </Card>
        </div>

        {/* geo + products */}
        <div className="grid gap-4 xl:grid-cols-2">
          {(dims.region?.values.length > 1 || dims.country?.values.length > 1) && (
            <Card>
              <CardHeader title={`${primaryLabel} by ${geo}`} subtitle="Click a bar to cross-filter the whole dashboard"
                right={<div className="flex items-center gap-2">
                  <Segmented label="Geography level" value={geo} onChange={setGeo} options={[...(dims.region?.values.length > 1 ? [{ value: 'region', label: 'Region' }] : []), { value: 'country', label: 'Country' }]} />
                  {csvHead(geoQ.data, 'geography')}
                </div>} />
              <div className="p-3 pt-2"><Body state={geoQ}>{(d) => <RankBars data={toBars(d, primary)} fmtKind={primaryFmt} onPick={(n) => setFilter(geo, [n])} activeNames={filters[geo] || []} color={PALETTE[1]} />}</Body></div>
            </Card>
          )}
          <Card>
            <CardHeader title="Top 10 products" subtitle="Ranked within the current filters"
              right={<div className="flex items-center gap-2">
                {money && <Segmented label="Product metric" value={prodMetric} onChange={setProdMetric} options={[{ value: 'revenue', label: 'Revenue' }, { value: 'profit', label: 'Profit' }, { value: 'orders', label: 'Orders' }]} />}
                {csvHead(prodQ.data, 'top_products')}
              </div>} />
            <div className="p-3 pt-2"><Body state={prodQ}>{(d) => <RankBars data={toBars(d, prodMetric)} fmtKind={prodMetric === 'orders' ? 'number' : 'currency'} color={PALETTE[2]} />}</Body></div>
          </Card>
        </div>

        {/* discount + heatmap + targets */}
        <div className={`grid gap-4 ${money ? 'xl:grid-cols-3' : 'xl:grid-cols-2'}`}>
          {money && (
            <Card>
              <CardHeader title="Discount depth vs profitability" subtitle="Loss-making orders (bars) and margin (line) by discount level" right={csvHead(discQ.data, 'discount_vs_margin')} />
              <div className="p-3 pt-4"><Body state={discQ}>{(d) => (
                <ComboChart data={discRows(d)} xFmt={(v) => dimLabel('discount', v)} height={250}
                  bar={{ key: 'loss_rate', name: 'Loss-making orders', fmt: 'percent', color: '#fb7185' }} line={{ key: 'margin', name: 'Profit margin', fmt: 'percent', color: '#34d399' }} />)}</Body></div>
            </Card>
          )}
          <Card>
            <CardHeader title={`Seasonality - ${primaryLabel.toLowerCase()} by month`} subtitle="Darker = stronger month" right={csvHead(heatQ.data, 'seasonality')} />
            <Body state={heatQ} h={200}>{(d) => <Heatmap cells={heatCells(d)} fmtKind={primaryFmt} />}</Body>
          </Card>
          <div className="no-print"><TargetsCard /></div>
        </div>

        {/* delivery + shipping + status */}
        <div className="grid gap-4 xl:grid-cols-3">
          <Card>
            <CardHeader title={`Delivery time by ${delivGeo}`} subtitle="Average days (bars) and share of deliveries over 15 days (line)" right={csvHead(delivQ.data, `delivery_by_${delivGeo}`)} />
            <div className="p-3 pt-4"><Body state={delivQ}>{(d) => (
              <ComboChart data={recs(d).map((r) => ({ x: r[delivGeo], ...r }))} height={250}
                bar={{ key: 'avg_shipping_days', name: 'Avg delivery days', fmt: 'days', color: PALETTE[0] }} line={{ key: 'slow_rate', name: 'Over 15 days', fmt: 'percent', color: '#fbbf24' }} />)}</Body></div>
          </Card>
          <Card>
            <CardHeader title="Shipping: speed vs cost" subtitle="Average delivery days and shipping cost per order, by method" right={csvHead(shipQ.data, 'shipping_methods')} />
            <div className="p-3 pt-4"><Body state={shipQ}>{(d) => (
              <ComboChart data={recs(d).map((r) => ({ x: r.shipping_method, ...r }))} height={250}
                bar={{ key: 'avg_shipping_cost', name: 'Avg shipping cost', fmt: 'currency', color: PALETTE[1] }} line={{ key: 'avg_shipping_days', name: 'Avg delivery days', fmt: 'days', color: '#fbbf24' }} />)}</Body></div>
          </Card>
          <Card>
            <CardHeader title="Order status" right={csvHead(statusQ.data, 'order_status')} />
            <div className="p-5"><Body state={statusQ} h={220}>{(d) => <Donut height={190} data={toBars(d, 'orders')} fmtKind="number" onPick={(n) => setFilter('status', [n])} activeNames={filters.status || []} />}</Body></div>
          </Card>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <Card>
            <CardHeader title="Returns & cancellations by category" right={csvHead(retQ.data, 'returns_by_category')} />
            <div className="p-3 pt-4"><Body state={retQ}>{(d) => (
              <ColBars data={recs(d).map((r) => ({ x: r.category, ...r }))} height={250}
                series={[{ key: 'return_rate', name: 'Return rate', fmt: 'percent', color: '#fbbf24' }, { key: 'cancel_rate', name: 'Cancel rate', fmt: 'percent', color: '#fb7185' }]} />)}</Body></div>
          </Card>
          <Card>
            <CardHeader title={money ? 'Customer segments' : 'Segments - orders and returns'} right={csvHead(segQ.data, 'segments')} />
            <div className="p-3 pt-4"><Body state={segQ}>{(d) => {
              const [a, b] = money ? ['revenue', 'aov'] : ['orders', 'return_rate']
              return <ComboChart data={recs(d).map((r) => ({ x: r.segment, ...r }))} height={250}
                bar={{ key: a, name: a === 'revenue' ? 'Net revenue' : 'Orders', fmt: a === 'revenue' ? 'currency' : 'number', color: PALETTE[2] }}
                line={{ key: b, name: b === 'aov' ? 'Avg order value' : 'Return rate', fmt: b === 'aov' ? 'currency' : 'percent', color: PALETTE[0] }} />
            }}</Body></div>
          </Card>
          <Card>
            <CardHeader title="Payment methods" subtitle="Share of orders" right={csvHead(payQ.data, 'payment_methods')} />
            <div className="p-5"><Body state={payQ} h={220}>{(d) => <Donut height={190} data={toBars(d, 'orders')} fmtKind="number" />}</Body></div>
          </Card>
        </div>
        <div className="pt-2 text-center text-[11px] text-[var(--body-muted)]/70">
          Net figures exclude returned and cancelled orders. All metrics are computed server-side within your role scope.
        </div>
      </div>
    </div>
  )
}

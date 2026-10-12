import { useMemo, useState } from 'react'
import { Lightbulb } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAsync, useFilters } from '../lib/filters'
import { PALETTE, dimLabel, fmt } from '../lib/format'
import { Body, recs, useQuery } from '../lib/query'
import { PageHeader } from '../components/Layout'
import FilterBar, { ActiveChips } from '../components/FilterBar'
import KpiCard from '../components/KpiCard'
import PrintHeader from '../components/PrintHeader'
import { CsvButton, PrintButton, RowsCsvButton } from '../components/tools'
import { Card, CardHeader, Segmented, Skeleton } from '../components/ui'
import { ColBars, ComboChart, TrendChart } from '../components/charts'

const KPI_KEYS = ['orders', 'avg_shipping_days', 'fast_rate', 'slow_rate', 'return_rate', 'cancel_rate', 'avg_shipping_cost', 'shipping_cost']

export default function Fulfilment() {
  const { meta } = useAuth()
  const { body } = useFilters()
  const dims = meta.options.dims
  const [lane, setLane] = useState(dims.region?.values.length > 1 ? 'region' : 'country')
  const kp = useAsync(() => api.kpis(body), [JSON.stringify(body)])
  const cards = (kp.data?.cards || []).filter((c) => KPI_KEYS.includes(c.key))

  const laneQ = useQuery({ metrics: ['avg_shipping_days', 'slow_rate', 'fast_rate', 'orders', 'return_rate', 'cancel_rate'], group_by: [lane] }, [lane])
  const bandQ = useQuery({ metrics: ['orders'], group_by: ['delivery_band'] })
  const methodQ = useQuery({ metrics: ['avg_shipping_days', 'avg_shipping_cost', 'orders'], group_by: ['shipping_method'] }, ['shipping_method'])
  const trendQ = useQuery({ metrics: ['avg_shipping_days'], group_by: ['month'] })
  const retQ = useQuery({ metrics: ['return_rate', 'cancel_rate'], group_by: [lane] }, [lane])
  const countryQ = useQuery({ metrics: ['avg_shipping_days', 'slow_rate', 'orders', 'return_rate'], group_by: ['country'] }, ['country'])

  const countries = useMemo(() => recs(countryQ.data).sort((a, b) => b.avg_shipping_days - a.avg_shipping_days), [countryQ.data])
  const callout = useMemo(() => {
    const l = recs(laneQ.data), m = recs(methodQ.data)
    if (l.length < 2 || m.length < 2) return null
    const spread = (rows) => Math.max(...rows.map((r) => r.avg_shipping_days)) - Math.min(...rows.map((r) => r.avg_shipping_days))
    const slow = [...l].sort((a, b) => b.avg_shipping_days - a.avg_shipping_days)[0]
    const fast = [...l].sort((a, b) => a.avg_shipping_days - b.avg_shipping_days)[0]
    return { by: lane, slow, fast, laneSpread: spread(l), methodSpread: spread(m) }
  }, [laneQ.data, methodQ.data, lane])

  return (
    <div className="pb-10">
      <PrintHeader title="Fulfilment report" />
      <PageHeader title="Fulfilment" subtitle="Delivery speed, returns and cancellations - where orders slow down and where they come back."><PrintButton /></PageHeader>
      <div className="no-print sticky top-0 z-20 border-b border-white/[0.06] bg-[rgba(4,5,12,0.5)] px-5 py-3 backdrop-blur-xl sm:px-10">
        <FilterBar />
        <div className="mt-2 empty:hidden"><ActiveChips /></div>
      </div>

      <div className="space-y-4 px-5 pt-5 sm:px-10">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {kp.data ? cards.slice(0, 8).map((c, i) => <KpiCard key={c.key} card={c} delay={i * 0.04} color={PALETTE[i % PALETTE.length]} />)
            : Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-[132px]" />)}
        </div>

        {callout && callout.laneSpread >= 2 && callout.laneSpread > 2 * callout.methodSpread && (
          <div className="glass flex items-start gap-3 rounded-2xl px-5 py-4 text-sm">
            <Lightbulb size={18} className="mt-0.5 shrink-0 text-amber-300" aria-hidden="true" />
            <p className="text-[var(--body-muted)]">
              <strong className="text-white">Delivery time depends on {callout.by}, not on shipping speed.</strong> {callout.slow[callout.by]} averages{' '}
              {callout.slow.avg_shipping_days.toFixed(1)} days versus {callout.fast.avg_shipping_days.toFixed(1)} for {callout.fast[callout.by]} ({callout.laneSpread.toFixed(1)}-day gap), while the four
              shipping methods differ by only {callout.methodSpread.toFixed(1)} days.
            </p>
          </div>
        )}

        <div className="grid gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader title={`Delivery time by ${lane}`} subtitle="Average days (bars) and share over 15 days (line)"
              right={<div className="flex items-center gap-2">
                {dims.region?.values.length > 1 && <Segmented label="Lane level" value={lane} onChange={setLane} options={[{ value: 'region', label: 'Region' }, { value: 'country', label: 'Country' }]} />}
                <CsvButton res={laneQ.data} name={`delivery_by_${lane}`} />
              </div>} />
            <div className="p-3 pt-4"><Body state={laneQ}>{(d) => <ComboChart data={recs(d).map((r) => ({ x: r[lane], ...r }))} height={260}
              bar={{ key: 'avg_shipping_days', name: 'Avg delivery days', fmt: 'days', color: PALETTE[0] }} line={{ key: 'slow_rate', name: 'Over 15 days', fmt: 'percent', color: '#fbbf24' }} />}</Body></div>
          </Card>
          <Card>
            <CardHeader title="How long do deliveries take?" subtitle="Orders by delivery time band" right={<CsvButton res={bandQ.data} name="delivery_bands" />} />
            <div className="p-3 pt-4"><Body state={bandQ}>{(d) => <ColBars data={recs(d).map((r) => ({ x: r.delivery_band, orders: r.orders }))} height={260}
              series={[{ key: 'orders', name: 'Orders', fmt: 'number', color: PALETTE[2] }]} />}</Body></div>
          </Card>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <Card>
            <CardHeader title="Shipping method: speed vs cost" right={<CsvButton res={methodQ.data} name="shipping_methods" />} />
            <div className="p-3 pt-4"><Body state={methodQ}>{(d) => <ComboChart data={recs(d).map((r) => ({ x: r.shipping_method, ...r }))} height={250}
              bar={{ key: 'avg_shipping_cost', name: 'Avg shipping cost', fmt: 'currency', color: PALETTE[1] }} line={{ key: 'avg_shipping_days', name: 'Avg delivery days', fmt: 'days', color: '#fbbf24' }} />}</Body></div>
          </Card>
          <Card>
            <CardHeader title={`Returns & cancellations by ${lane}`} right={<CsvButton res={retQ.data} name={`returns_by_${lane}`} />} />
            <div className="p-3 pt-4"><Body state={retQ}>{(d) => <ColBars data={recs(d).map((r) => ({ x: r[lane], ...r }))} height={250}
              series={[{ key: 'return_rate', name: 'Return rate', fmt: 'percent', color: '#fbbf24' }, { key: 'cancel_rate', name: 'Cancel rate', fmt: 'percent', color: '#fb7185' }]} />}</Body></div>
          </Card>
          <Card>
            <CardHeader title="Delivery time trend" subtitle="Average days by month" right={<CsvButton res={trendQ.data} name="delivery_trend" />} />
            <div className="p-3 pt-4"><Body state={trendQ}>{(d) => <TrendChart data={recs(d).map((r) => ({ x: r.month, ...r }))} height={250} kind="line" xFmt={(v) => dimLabel('month', v)}
              series={[{ key: 'avg_shipping_days', name: 'Avg delivery days', fmt: 'days', color: PALETTE[0] }]} />}</Body></div>
          </Card>
        </div>

        <Card className="overflow-hidden">
          <CardHeader title="Slowest lanes" subtitle="Countries ranked by average delivery time"
            right={<RowsCsvButton name="lanes" columns={['Country', 'Orders', 'Avg delivery days', 'Over 15 days %', 'Return rate %']}
              rows={countries.map((r) => [r.country, r.orders, r.avg_shipping_days, r.slow_rate, r.return_rate])} />} />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead><tr className="border-y border-white/[0.07] text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
                {['Country', 'Orders', 'Avg delivery', 'Over 15 days', 'Return rate'].map((h, i) => <th key={h} scope="col" className={`px-4 py-3 font-medium ${i ? 'text-right' : ''}`}>{h}</th>)}</tr></thead>
              <tbody>{countries.map((r) => (
                <tr key={r.country} className="border-b border-white/[0.04] hover:bg-white/[0.04]">
                  <td className="px-4 py-2 font-medium text-white">{r.country}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt('number', r.orders)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt('days', r.avg_shipping_days)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt('percent', r.slow_rate)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt('percent', r.return_rate)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}

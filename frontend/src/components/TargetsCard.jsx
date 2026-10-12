import { useState } from 'react'
import { Target, X } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAsync } from '../lib/filters'
import { fmt } from '../lib/format'
import { Card, CardHeader, ErrorBox } from './ui'

/** Personal targets: set a yearly target for a metric and track actual vs target within your own data scope. */
export default function TargetsCard() {
  const { meta } = useAuth()
  const metrics = ['revenue', 'profit', 'orders'].filter((k) => meta.metrics.some((m) => m.key === k))
  const years = [...(meta.options.dims.year?.values || [])].reverse()
  const [tick, setTick] = useState(0)
  const [metric, setMetric] = useState(metrics[0])
  const [year, setYear] = useState(years[0])
  const [value, setValue] = useState('')
  const [err, setErr] = useState('')
  const state = useAsync(() => api.targets(), [tick])

  const save = async (e) => {
    e.preventDefault()
    setErr('')
    const n = Number(String(value).replace(/[, $]/g, ''))
    try {
      await api.setTarget(metric, Number(year), n)
      setValue('')
      setTick((t) => t + 1)
    } catch (ex) { setErr(ex.message) }
  }
  const remove = async (t) => { await api.deleteTarget(t.metric, t.year); setTick((x) => x + 1) }
  const sel = 'rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[0.78rem] text-white outline-none focus:border-white/40'

  return (
    <Card className="flex flex-col">
      <CardHeader title="Targets" subtitle="Your own yearly goals, tracked within your data scope" right={<Target size={18} className="mt-1 text-[var(--body-muted)]" aria-hidden="true" />} />
      <div className="flex-1 space-y-3 px-6 pb-5 pt-4">
        {state.error && <ErrorBox error={state.error} />}
        {(state.data || []).map((t) => {
          const pct = Math.max(0, Math.min(130, t.pct ?? 0))
          const hit = (t.pct ?? 0) >= 100
          return (
            <div key={`${t.metric}-${t.year}`}>
              <div className="flex items-center justify-between text-[0.8rem]">
                <span className="text-[var(--heading)]">{t.label} {t.year}</span>
                <span className="flex items-center gap-2 text-[var(--body-muted)]">
                  {fmt(t.fmt, t.actual, { short: true })} of {fmt(t.fmt, t.target, { short: true })}
                  <button onClick={() => remove(t)} aria-label={`Remove ${t.label} ${t.year} target`} className="rounded-full p-0.5 hover:bg-white/10 hover:text-white"><X size={13} /></button>
                </span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuenow={Math.round(t.pct ?? 0)} aria-valuemin={0} aria-valuemax={100} aria-label={`${t.label} ${t.year} progress`}>
                <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(100, pct)}%`, background: hit ? '#34d399' : 'linear-gradient(90deg,#5ee1ff,#a78bfa)' }} />
              </div>
              <div className="mt-1 text-[0.7rem] text-[var(--body-muted)]/80">
                {hit ? `Target reached (${t.pct}%)` : `${t.pct}% reached - ${fmt(t.fmt, t.gap, { short: true })} to go`}
              </div>
            </div>
          )
        })}
        {state.data && !state.data.length && <p className="text-[0.8rem] text-[var(--body-muted)]">No targets yet. Set one below to track progress here.</p>}
        <form onSubmit={save} className="flex flex-wrap items-center gap-2 pt-1">
          <select aria-label="Metric" value={metric} onChange={(e) => setMetric(e.target.value)} className={sel}>
            {metrics.map((m) => <option key={m} value={m} className="bg-[#0b0d1a]">{meta.metrics.find((x) => x.key === m).label}</option>)}
          </select>
          <select aria-label="Year" value={year} onChange={(e) => setYear(e.target.value)} className={sel}>
            {years.map((y) => <option key={y} value={y} className="bg-[#0b0d1a]">{y}</option>)}
          </select>
          <input aria-label="Target value" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Target" className={`${sel} w-28`} />
          <button className="pill-btn !h-8 !px-4 !text-[0.78rem]" disabled={!value}>Save</button>
        </form>
        {err && <p className="text-[0.75rem] text-rose-300">{err}</p>}
      </div>
    </Card>
  )
}

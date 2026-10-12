import { useEffect, useRef, useState } from 'react'
import { CalendarRange, Check, ChevronDown, RotateCcw, SlidersHorizontal, X } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { useFilters } from '../lib/filters'
import { Segmented } from './ui'
import { cx } from '../lib/format'

const PRIMARY = ['year', 'region', 'country', 'category', 'segment', 'status']
const MORE = ['quarter_of_year', 'season', 'sub_category', 'gender', 'shipping_method', 'payment_method']

/** closes a popover on outside click or Escape */
function usePopover() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const down = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    const key = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', down)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key) }
  }, [open])
  return { open, setOpen, ref }
}

function MultiSelect({ label, values, selected, onChange }) {
  const { open, setOpen, ref } = usePopover()
  const sel = selected.map(String)
  const toggle = (v) => onChange(sel.includes(String(v)) ? sel.filter((x) => x !== String(v)) : [...sel, String(v)])
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cx(
          'flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[0.78rem] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70',
          sel.length ? 'border-white/35 bg-white/15 text-white' : 'glass text-[var(--body-muted)] hover:text-white',
        )}
      >
        {label}
        {sel.length > 0 && <span className="rounded-full bg-white/20 px-1.5 text-[10px]">{sel.length === 1 ? sel[0] : sel.length}</span>}
        <ChevronDown size={13} className={cx('transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </button>
      {open && (
        <div role="listbox" aria-label={label} aria-multiselectable="true"
          className="absolute left-0 top-full z-30 mt-1.5 max-h-72 w-52 overflow-auto rounded-2xl border border-white/10 bg-[#0b0d1a]/95 p-1 shadow-2xl backdrop-blur">
          {values.map((v) => {
            const on = sel.includes(String(v))
            return (
              <button key={v} role="option" aria-selected={on} onClick={() => toggle(v)}
                className="flex w-full items-center justify-between rounded-xl px-3 py-1.5 text-left text-xs text-[var(--heading)] hover:bg-white/10 focus-visible:bg-white/10 focus-visible:outline-none">
                {String(v)}
                {on && <Check size={13} className="text-cyan-200" aria-hidden="true" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

const iso = (d) => d.toISOString().slice(0, 10)
const addDays = (s, n) => { const d = new Date(`${s}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return iso(d) }

function DateRange({ min, max }) {
  const { filters, setRange } = useFilters()
  const { open, setOpen, ref } = usePopover()
  const from = filters.date_from || ''
  const to = filters.date_to || ''
  const active = Boolean(from || to)
  const presets = [
    ['All time', '', ''],
    ['Last 90 days of data', addDays(max, -89), max],
    ['Last 12 months of data', addDays(max, -364), max],
    [`Year to date (${max.slice(0, 4)})`, `${max.slice(0, 4)}-01-01`, max],
  ]
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} aria-haspopup="dialog" aria-expanded={open}
        className={cx('flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[0.78rem] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70',
          active ? 'border-white/35 bg-white/15 text-white' : 'glass text-[var(--body-muted)] hover:text-white')}>
        <CalendarRange size={13} aria-hidden="true" />
        {active ? `${from || min} → ${to || max}` : 'Date range'}
        <ChevronDown size={13} className={cx('transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </button>
      {open && (
        <div role="dialog" aria-label="Date range" className="absolute left-0 top-full z-30 mt-1.5 w-72 rounded-2xl border border-white/10 bg-[#0b0d1a]/95 p-3 shadow-2xl backdrop-blur">
          <div className="grid grid-cols-2 gap-2">
            <label className="text-[0.7rem] text-[var(--body-muted)]">From
              <input type="date" min={min} max={to || max} value={from} onChange={(e) => setRange(e.target.value, to)}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white outline-none focus:border-white/40" />
            </label>
            <label className="text-[0.7rem] text-[var(--body-muted)]">To
              <input type="date" min={from || min} max={max} value={to} onChange={(e) => setRange(from, e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white outline-none focus:border-white/40" />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {presets.map(([label, f, t]) => (
              <button key={label} onClick={() => { setRange(f, t); setOpen(false) }} className="pill-ghost px-2.5 py-1 text-[0.7rem]">{label}</button>
            ))}
          </div>
          <p className="mt-2.5 text-[0.65rem] text-[var(--body-muted)]/70">Data covers {min} to {max}.</p>
        </div>
      )}
    </div>
  )
}

export default function FilterBar({ show }) {
  const { meta } = useAuth()
  const { filters, setFilter, basis, setBasis, clear, active } = useFilters()
  const [more, setMore] = useState(false)
  const dims = meta.options.dims
  const [min, max] = meta.options.date_range
  const usable = (list) => list.filter((k) => dims[k] && dims[k].values.length > 1 && (!show || show.includes(k)))
  const secondary = usable(MORE)
  const moreActive = secondary.filter((k) => filters[k]?.length).length

  return (
    <div className="flex flex-col gap-2" role="search" aria-label="Filters">
      <div className="flex flex-wrap items-center gap-2">
        <DateRange min={min} max={max} />
        {usable(PRIMARY).map((k) => (
          <MultiSelect key={k} label={dims[k].label} values={dims[k].values} selected={filters[k] || []} onChange={(v) => setFilter(k, v)} />
        ))}
        {secondary.length > 0 && (
          <button onClick={() => setMore(!more)} aria-expanded={more}
            className={cx('flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[0.78rem] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70',
              moreActive ? 'border-white/35 bg-white/15 text-white' : 'glass text-[var(--body-muted)] hover:text-white')}>
            <SlidersHorizontal size={13} aria-hidden="true" /> More{moreActive > 0 && <span className="rounded-full bg-white/20 px-1.5 text-[10px]">{moreActive}</span>}
          </button>
        )}
        {active > 0 && (
          <button onClick={clear} className="flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs text-[var(--body-muted)] hover:text-white">
            <RotateCcw size={12} aria-hidden="true" /> Reset
          </button>
        )}
        <div className="ml-auto flex items-center gap-2" title="Net excludes returned and cancelled orders">
          <span className="text-[11px] uppercase tracking-wider text-[var(--body-muted)]/70" id="basis-label">Basis</span>
          <Segmented value={basis} onChange={setBasis} label="Revenue basis" options={[{ value: 'net', label: 'Net' }, { value: 'gross', label: 'Gross' }]} />
        </div>
      </div>
      {more && secondary.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {secondary.map((k) => (
            <MultiSelect key={k} label={dims[k].label} values={dims[k].values} selected={filters[k] || []} onChange={(v) => setFilter(k, v)} />
          ))}
        </div>
      )}
    </div>
  )
}

export function ActiveChips() {
  const { meta } = useAuth()
  const { filters, setFilter, setRange } = useFilters()
  const dims = meta.options.dims
  const chips = Object.entries(filters).filter(([k]) => !k.startsWith('date_')).flatMap(([k, vs]) => vs.map((v) => [k, v]))
  const range = filters.date_from || filters.date_to
  if (!chips.length && !range) return null
  const chip = 'flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] text-[var(--body-muted)] hover:bg-white/10'
  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Active filters">
      {range && (
        <button onClick={() => setRange('', '')} className={chip} aria-label="Remove date range filter">
          {filters.date_from || '…'} → {filters.date_to || '…'} <X size={11} aria-hidden="true" />
        </button>
      )}
      {chips.map(([k, v]) => (
        <button key={`${k}-${v}`} onClick={() => setFilter(k, (filters[k] || []).filter((x) => String(x) !== String(v)))} className={chip}
          aria-label={`Remove filter ${dims[k]?.label || k}: ${v}`}>
          <span className="text-[var(--body-muted)]/70">{dims[k]?.label || k}:</span> {String(v)} <X size={11} aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}

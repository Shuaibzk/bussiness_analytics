import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { PALETTE, fmt } from '../lib/format'
import { Empty } from './ui'

const AXIS = { stroke: 'rgba(255,255,255,0.28)', fontSize: 11, tickLine: false, axisLine: false }
const GRID = <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />

export function ChartTip({ active, payload, label, formats = {}, labelFmt }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-white/10 bg-[rgba(8,10,22,0.92)] px-3 py-2 text-xs shadow-2xl backdrop-blur">
      <div className="mb-1 font-medium text-[var(--heading)]">{labelFmt ? labelFmt(label) : label}</div>
      {payload.map((p) => (
        <div key={p.dataKey ?? p.name} className="flex items-center gap-2 text-[var(--body-muted)]">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.payload?.fill }} />
          <span>{p.name}</span>
          <span className="ml-auto pl-4 font-medium text-white">{fmt(formats[p.dataKey] || formats[p.name] || 'number', p.value)}</span>
        </div>
      ))}
    </div>
  )
}

/** series: [{key, name, fmt}] ; data: [{x, ...}] */
export function TrendChart({ data, series, height = 280, kind = 'area', xFmt }) {
  if (!data?.length) return <Empty />
  const formats = Object.fromEntries(series.map((s) => [s.key, s.fmt]))
  const Chart = kind === 'line' ? LineChart : AreaChart
  return (
    <ResponsiveContainer width="100%" height={height}>
      <Chart data={data} margin={{ top: 10, right: 12, left: -8, bottom: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`tg-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color || PALETTE[i]} stopOpacity={0.4} />
              <stop offset="100%" stopColor={s.color || PALETTE[i]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        {GRID}
        <XAxis dataKey="x" {...AXIS} tickFormatter={xFmt} minTickGap={22} />
        <YAxis {...AXIS} tickFormatter={(v) => fmt(series[0].fmt, v, { short: true })} width={56} />
        <Tooltip content={<ChartTip formats={formats} labelFmt={xFmt} />} cursor={{ stroke: 'rgba(255,255,255,0.15)' }} />
        {series.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: '#9aa0b8' }} />}
        {series.map((s, i) => kind === 'line'
          ? <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color || PALETTE[i]} strokeWidth={2.2} dot={false} activeDot={{ r: 4 }} />
          : <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color || PALETTE[i]} strokeWidth={2.2} fill={`url(#tg-${s.key})`} />)}
      </Chart>
    </ResponsiveContainer>
  )
}

/** history (solid) + projection (dashed) with a shaded uncertainty band. rows: [{x, actual?, forecast?, band?: [low, high]}] */
export function ForecastChart({ rows, fmtKind, height = 290, xFmt }) {
  if (!rows?.length) return <Empty />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 10, right: 12, left: -8, bottom: 0 }}>
        {GRID}
        <XAxis dataKey="x" {...AXIS} tickFormatter={xFmt} minTickGap={22} />
        <YAxis {...AXIS} tickFormatter={(v) => fmt(fmtKind, v, { short: true })} width={56} />
        <Tooltip content={<ChartTip formats={{ actual: fmtKind, forecast: fmtKind, band: fmtKind }} labelFmt={xFmt} />} cursor={{ stroke: 'rgba(255,255,255,0.15)' }} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: '#9aa0b8' }} />
        <Area dataKey="band" name="Likely range" stroke="none" fill={PALETTE[2]} fillOpacity={0.2} isAnimationActive={false} />
        <Line type="monotone" dataKey="actual" name="Actual" stroke={PALETTE[0]} strokeWidth={2.4} dot={false} connectNulls />
        <Line type="monotone" dataKey="forecast" name="Forecast" stroke={PALETTE[3]} strokeWidth={2.4} strokeDasharray="6 5" dot={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Horizontal ranked bars; data: [{name, value}] */
export function RankBars({ data, fmtKind, height, color = PALETTE[0], onPick, activeNames = [] }) {
  if (!data?.length) return <Empty />
  const h = height || Math.max(180, data.length * 34 + 20)
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 64, left: 0, bottom: 0 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" {...AXIS} width={118} tick={{ fill: '#aeb4cc', fontSize: 12 }} />
        <Tooltip content={<ChartTip formats={{ value: fmtKind }} />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar dataKey="value" name="Value" radius={[0, 8, 8, 0]} barSize={16} onClick={(d) => onPick?.(d.name)} cursor={onPick ? 'pointer' : undefined}
          label={{ position: 'right', fill: '#c9cee3', fontSize: 11, formatter: (v) => fmt(fmtKind, v, { short: true }) }}>
          {data.map((d, i) => (
            <Cell key={d.name} fill={color} fillOpacity={activeNames.length && !activeNames.includes(d.name) ? 0.35 : 1 - i * 0.02} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function ColBars({ data, series, fmtKind, height = 260, onPick, xFmt, stacked }) {
  if (!data?.length) return <Empty />
  const formats = Object.fromEntries(series.map((s) => [s.key, s.fmt || fmtKind]))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 10, right: 8, left: -8, bottom: 0 }}>
        {GRID}
        <XAxis dataKey="x" {...AXIS} tickFormatter={xFmt} interval={0} tick={{ fill: 'rgba(255,255,255,0.45)', fontSize: 10 }} />
        <YAxis {...AXIS} tickFormatter={(v) => fmt(series[0].fmt || fmtKind, v, { short: true })} width={52} />
        <Tooltip content={<ChartTip formats={formats} labelFmt={xFmt} />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        {series.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: '#9aa0b8' }} />}
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} stackId={stacked ? 'a' : undefined} fill={s.color || PALETTE[i]}
            radius={stacked ? 0 : [6, 6, 0, 0]} maxBarSize={44} onClick={(d) => onPick?.(d.x)} cursor={onPick ? 'pointer' : undefined} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

export function Donut({ data, fmtKind, height = 190, onPick, activeNames = [] }) {
  if (!data?.length) return <Empty />
  const total = data.reduce((s, d) => s + (d.value || 0), 0)
  return (
    <div className="flex items-center gap-4">
      <div className="relative shrink-0" style={{ width: height, height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius="64%" outerRadius="92%" paddingAngle={2} stroke="none"
              onClick={(d) => onPick?.(d.name)} cursor={onPick ? 'pointer' : undefined}>
              {data.map((d, i) => <Cell key={d.name} fill={PALETTE[i % PALETTE.length]} fillOpacity={activeNames.length && !activeNames.includes(d.name) ? 0.3 : 1} />)}
            </Pie>
            <Tooltip content={<ChartTip formats={{ value: fmtKind }} />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="text-xl font-medium">{fmt(fmtKind, total, { short: true })}</div>
            <div className="text-[11px] text-[var(--body-muted)]">total</div>
          </div>
        </div>
      </div>
      <ul className="min-w-0 flex-1 space-y-1.5 text-xs">
        {data.map((d, i) => (
          <li key={d.name} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="truncate text-[var(--body-muted)]">{d.name}</span>
            <span className="ml-auto pl-2 font-medium text-white">{total ? ((d.value / total) * 100).toFixed(0) : 0}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** bars (left axis) + line (right axis) */
export function ComboChart({ data, bar, line, height = 270, xFmt }) {
  if (!data?.length) return <Empty />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 10, right: 6, left: -8, bottom: 0 }}>
        {GRID}
        <XAxis dataKey="x" {...AXIS} tickFormatter={xFmt} interval={0} tick={{ fill: 'rgba(255,255,255,0.45)', fontSize: 10 }} />
        <YAxis yAxisId="l" {...AXIS} tickFormatter={(v) => fmt(bar.fmt, v, { short: true })} width={44} />
        <YAxis yAxisId="r" orientation="right" {...AXIS} tickFormatter={(v) => fmt(line.fmt, v, { short: true })} width={44} />
        <Tooltip content={<ChartTip formats={{ [bar.key]: bar.fmt, [line.key]: line.fmt }} labelFmt={xFmt} />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: '#9aa0b8' }} />
        <Bar yAxisId="l" dataKey={bar.key} name={bar.name} fill={bar.color} radius={[6, 6, 0, 0]} maxBarSize={36} fillOpacity={0.85} />
        <Line yAxisId="r" type="monotone" dataKey={line.key} name={line.name} stroke={line.color} strokeWidth={2.4} dot={{ r: 3, fill: line.color }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** rows: years, cols: 12 months; cells: {year, month, value} */
export function Heatmap({ cells, fmtKind }) {
  if (!cells?.length) return <Empty />
  const years = [...new Set(cells.map((c) => c.year))].sort()
  const max = Math.max(...cells.map((c) => c.value || 0)) || 1
  const get = (y, m) => cells.find((c) => c.year === y && c.month === m)
  const M = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
  return (
    <div className="px-5 pb-5 pt-3">
      <div className="grid gap-1" style={{ gridTemplateColumns: `44px repeat(12, minmax(0, 1fr))` }}>
        <div />
        {M.map((m, i) => <div key={i} className="text-center text-[10px] text-[var(--body-muted)]/70">{m}</div>)}
        {years.map((y) => (
          <div key={y} className="contents">
            <div className="flex items-center text-[11px] text-[var(--body-muted)]">{y}</div>
            {Array.from({ length: 12 }, (_, i) => {
              const c = get(y, i + 1)
              const t = c ? c.value / max : 0
              return (
                <div key={i} title={c ? `${y}-${String(i + 1).padStart(2, '0')}: ${fmt(fmtKind, c.value)}` : 'No data'}
                  className="aspect-[1.25] rounded-md transition-transform hover:scale-110"
                  style={{ background: c ? `rgba(94,225,255,${0.08 + t * 0.85})` : 'rgba(255,255,255,0.03)', boxShadow: t > 0.8 ? '0 0 14px rgba(94,225,255,0.45)' : 'none' }} />
              )
            })}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-end gap-2 text-[10px] text-[var(--body-muted)]/70">
        low <div className="h-1.5 w-24 rounded-full" style={{ background: 'linear-gradient(90deg, rgba(94,225,255,0.1), rgba(94,225,255,0.93))' }} /> high
      </div>
    </div>
  )
}

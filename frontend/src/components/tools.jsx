import { Download, Printer } from 'lucide-react'
import { downloadCsv } from '../lib/api'
import { dimLabel } from '../lib/format'

/** CSV download of a governed query result the user is already looking at */
export function CsvButton({ res, name }) {
  if (!res?.rows?.length) return null
  const go = () => downloadCsv(
    `panorama_${name}.csv`,
    res.columns.map((c) => c.label),
    res.rows.map((r) => r.map((v, i) => (res.columns[i].role === 'dimension' ? dimLabel(res.columns[i].key, v) : v))),
  )
  return (
    <button onClick={go} className="no-print grid h-8 w-8 place-items-center rounded-full text-[var(--body-muted)] transition-colors hover:bg-white/10 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70"
      title="Download this chart's data (CSV)" aria-label={`Download ${name} data as CSV`}>
      <Download size={15} aria-hidden="true" />
    </button>
  )
}

/** CSV from arbitrary rows (tables that are not raw query results) */
export function RowsCsvButton({ name, columns, rows }) {
  if (!rows?.length) return null
  return (
    <button onClick={() => downloadCsv(`panorama_${name}.csv`, columns, rows)}
      className="no-print grid h-8 w-8 place-items-center rounded-full text-[var(--body-muted)] transition-colors hover:bg-white/10 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70"
      title="Download this table (CSV)" aria-label={`Download ${name} as CSV`}>
      <Download size={15} aria-hidden="true" />
    </button>
  )
}

export function PrintButton({ label = 'Print / save as PDF' }) {
  return (
    <button onClick={() => window.print()} className="pill-ghost no-print px-4 py-2 text-[0.85rem]" title="Opens the print dialog - choose 'Save as PDF'">
      <Printer size={14} aria-hidden="true" /> {label}
    </button>
  )
}

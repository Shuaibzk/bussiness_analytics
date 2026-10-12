import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { useFilters } from '../lib/filters'

/** Letterhead that only appears when the page is printed / saved as PDF */
export default function PrintHeader({ title }) {
  const { user, meta } = useAuth()
  const { basis, filters } = useFilters()
  const [stamp] = useState(() => new Date().toLocaleString())
  const [min, max] = meta.options.date_range
  const parts = Object.entries(filters).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(', ') : v}`)
  return (
    <div className="print-only mb-4 border-b border-black/30 pb-3">
      <div className="text-xl font-medium">Panorama - {title}</div>
      <div className="mt-1 text-[11px]">
        Prepared for {user.name} ({user.role_label}{user.scope ? `, ${user.scope.value} only` : ''}) on {stamp} -
        data {min} to {max} - {basis === 'net' ? 'net of returns and cancellations' : 'gross (all orders)'}
        {parts.length ? ` - filters: ${parts.join('; ')}` : ''}
      </div>
    </div>
  )
}

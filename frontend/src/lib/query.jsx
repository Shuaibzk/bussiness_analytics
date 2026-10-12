import { api } from './api'
import { useAsync, useFilters } from './filters'
import { ErrorBox, Skeleton } from '../components/ui'

/** run a governed query with the global filters; `ignore` lets a chart keep showing every value of its own dimension */
export function useQuery(q, ignore = [], forceBasis) {
  const { filters, basis: globalBasis } = useFilters()
  const basis = forceBasis || globalBasis
  const f = { ...filters }
  ignore.forEach((k) => delete f[k])
  return useAsync(() => api.query({ ...q, filters: f, basis }), [JSON.stringify(q), JSON.stringify(f), basis])
}

/** [{dimension: value, metric: value}, ...] from a query result */
export const recs = (res) => {
  if (!res) return []
  const keys = res.columns.map((c) => c.key)
  return res.rows.map((r) => Object.fromEntries(keys.map((k, i) => [k, r[i]])))
}

export function Body({ state, children, h = 260 }) {
  if (state.error) return <div className="p-5"><ErrorBox error={state.error} /></div>
  if (state.loading && !state.data) return <div className="p-5"><Skeleton className="w-full" style={{ height: h }} /></div>
  return <div className={state.loading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>{children(state.data)}</div>
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

/** Global dashboard filters, kept in the URL so views are shareable and survive refresh. */
const FilterCtx = createContext(null)
export const useFilters = () => useContext(FilterCtx)

const KEYS = ['year', 'quarter_of_year', 'season', 'region', 'country', 'category', 'sub_category', 'segment', 'gender',
  'shipping_method', 'payment_method', 'status']
const ISO = /^\d{4}-\d{2}-\d{2}$/

export function FilterProvider({ children }) {
  const [params, setParams] = useSearchParams()

  const filters = useMemo(() => {
    const f = {}
    for (const k of KEYS) {
      const v = params.getAll(k)
      if (v.length) f[k] = k === 'year' ? v.map(Number) : v
    }
    for (const k of ['date_from', 'date_to']) {
      const v = params.get(k)
      if (v && ISO.test(v)) f[k] = v // single ISO dates (the server compares them to order_date)
    }
    return f
  }, [params])
  const basis = params.get('basis') === 'gross' ? 'gross' : 'net'

  const setFilter = useCallback((key, values) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete(key)
      ;(values || []).forEach((v) => next.append(key, v))
      return next
    }, { replace: true })
  }, [setParams])

  const setRange = useCallback((from, to) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      from ? next.set('date_from', from) : next.delete('date_from')
      to ? next.set('date_to', to) : next.delete('date_to')
      return next
    }, { replace: true })
  }, [setParams])

  const setBasis = useCallback((b) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      b === 'gross' ? next.set('basis', 'gross') : next.delete('basis')
      return next
    }, { replace: true })
  }, [setParams])

  const clear = useCallback(() => setParams((prev) => {
    const next = new URLSearchParams()
    if (prev.get('basis')) next.set('basis', prev.get('basis'))
    return next
  }, { replace: true }), [setParams])

  const body = useMemo(() => ({ filters, basis }), [filters, basis])
  const key = JSON.stringify(body)
  const value = useMemo(
    () => ({ filters, basis, setFilter, setRange, setBasis, clear, body, key, active: Object.keys(filters).length }),
    [filters, basis, setFilter, setRange, setBasis, clear, body, key],
  )
  return <FilterCtx.Provider value={value}>{children}</FilterCtx.Provider>
}

/** tiny data-fetching hook with loading / error and automatic cancellation of stale responses */
export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn().then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((error) => alive && setState({ data: null, loading: false, error }))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}

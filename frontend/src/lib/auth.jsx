import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api, setUnauthorizedHandler } from './api'

const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)

export function AuthProvider({ children }) {
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const metaRef = useRef(null)
  useEffect(() => { metaRef.current = meta }, [meta])

  const refresh = useCallback(async (quiet = false) => {
    const m = await api.meta(quiet)
    setMeta(m)
    return m
  }, [])

  const clear = useCallback((why) => {
    setMeta(null)
    if (why) setNotice(why)
  }, [])

  const logout = useCallback(async () => {
    await api.logout()
    clear()
  }, [clear])

  useEffect(() => {
    // any 401 after sign-in means the session ended (idle timeout, revoked, password changed elsewhere)
    setUnauthorizedHandler(() => {
      if (!metaRef.current) return
      setNotice('Your session ended. Please sign in again.')
      setMeta(null)
    })
    refresh(true).catch(() => {}).finally(() => setLoading(false))  // the cookie (if any) identifies us
  }, [refresh])

  const login = useCallback(async (username, password) => {
    setNotice('')
    await api.login(username, password)
    return refresh()
  }, [refresh])

  const value = useMemo(() => ({ meta, user: meta?.user, loading, notice, login, logout, refresh }), [meta, loading, notice, login, logout, refresh])
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

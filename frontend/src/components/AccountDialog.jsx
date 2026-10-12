import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../lib/api'

/** Change-password dialog (focus-trapped enough for a single form: first field focused, Escape closes) */
export default function AccountDialog({ onClose }) {
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [msg, setMsg] = useState({ ok: false, text: '' })
  const [busy, setBusy] = useState(false)
  const first = useRef(null)
  useEffect(() => {
    first.current?.focus()
    const key = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [onClose])

  const submit = async (e) => {
    e.preventDefault()
    if (next !== again) return setMsg({ ok: false, text: 'The new passwords do not match.' })
    setBusy(true)
    try {
      await api.changePassword(cur, next)
      setMsg({ ok: true, text: 'Password changed. Your other sessions were signed out.' })
      setCur(''); setNext(''); setAgain('')
    } catch (err) { setMsg({ ok: false, text: err.message }) } finally { setBusy(false) }
  }
  const field = 'w-full rounded-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-white/40'
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="pw-title" className="panel w-full max-w-[26rem] rounded-[1.5rem] p-6">
        <div className="flex items-center justify-between">
          <h2 id="pw-title" className="text-[1.2rem] font-medium">Change password</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-full p-1.5 hover:bg-white/10"><X size={16} /></button>
        </div>
        <div className="mt-5 space-y-3">
          <label className="block text-xs text-[var(--body-muted)]">Current password
            <input ref={first} type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} className={`${field} mt-1`} required />
          </label>
          <label className="block text-xs text-[var(--body-muted)]">New password
            <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className={`${field} mt-1`} required />
          </label>
          <label className="block text-xs text-[var(--body-muted)]">Repeat new password
            <input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} className={`${field} mt-1`} required />
          </label>
          <p className="text-[0.7rem] text-[var(--body-muted)]/80">At least 8 characters, with letters and a digit.</p>
        </div>
        {msg.text && <p role="status" className={`mt-3 text-[0.8rem] ${msg.ok ? 'text-emerald-300' : 'text-rose-300'}`}>{msg.text}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="pill-ghost px-4 py-2 text-sm">Close</button>
          <button className="pill-btn" disabled={busy || !cur || !next || !again}>{busy ? 'Saving…' : 'Update password'}</button>
        </div>
      </form>
    </div>
  )
}

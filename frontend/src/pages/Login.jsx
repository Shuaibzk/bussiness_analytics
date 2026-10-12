import { useEffect, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import FluidBackground from '../components/FluidBackground'
import { Reveal, Words } from '../components/Reveal'
import { Logo } from '../components/ui'

export default function Login() {
  const { login, notice } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [accounts, setAccounts] = useState([])
  useEffect(() => { api.demoAccounts().then(setAccounts).catch(() => {}) }, [])

  const submit = async (e, u = username, p = password) => {
    e?.preventDefault()
    setBusy(true); setError('')
    try { await login(u, p) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const demo = (a) => { setUsername(a.username); setPassword(a.password); submit(null, a.username, a.password) }
  const admin = accounts.find((a) => a.role === 'admin')

  return (
    <section className="relative flex min-h-[100lvh] w-screen flex-col items-center justify-center overflow-hidden bg-[var(--hero-base)] px-5 py-28 text-center sm:px-10">
      <FluidBackground variant="hero" />

      {/* top nav */}
      <Reveal as="header" delay={150} from="-0.75rem" className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-5 py-5 sm:px-10 sm:py-7">
        <Logo />
        {admin && <button className="pill-btn" onClick={() => demo(admin)} disabled={busy}>Try the demo <ArrowRight size={15} aria-hidden="true" /></button>}
      </Reveal>

      {/* centre column */}
      <div className="relative z-10 flex w-full max-w-[22rem] flex-col items-center sm:max-w-[40rem] lg:max-w-[52rem]">
        <Reveal as="p" delay={320} className="glass inline-flex items-center rounded-full px-[0.875rem] py-[0.4rem] text-[0.72rem] text-[var(--body-muted)] sm:text-[0.8rem]">
          10,000 orders · 4 regions · 5 access roles
        </Reveal>

        <h1 className="mt-5 max-w-[20rem] text-[2rem] font-medium leading-[1.1] tracking-[-0.02em] text-[var(--heading)] sm:mt-7 sm:max-w-[34rem] sm:text-[3.5rem] lg:max-w-[46rem] lg:text-[5rem]">
          <Words text="Analytics that know who is asking" delay={480} stagger={85} duration={720} y={26} />
        </h1>

        <p className="mt-4 max-w-[20rem] text-[1rem] leading-normal text-[var(--body-muted)] sm:mt-5 sm:max-w-[34rem] sm:text-[1.1rem] lg:max-w-none lg:text-[1.2rem]">
          <Words text="Explore global e-commerce performance with an AI analyst that answers from your data and respects your access level." delay={1150} stagger={22} duration={600} y={14} />
        </p>

        <Reveal delay={1450} className="mt-7 flex w-full flex-col items-center sm:mt-10">
          <form onSubmit={submit} className="w-[37rem] max-w-full">
            <div className="glass flex h-14 items-center rounded-full pl-5 pr-[0.35rem] shadow-[0_1px_2px_rgba(0,0,0,0.05)] sm:h-16 sm:pl-6 sm:pr-[0.4rem]">
              <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" autoComplete="username" aria-label="Username"
                className="h-full min-w-0 flex-1 bg-transparent text-[0.95rem] text-[var(--heading)] outline-none sm:text-[1.15rem]" />
              <span className="mx-2 h-6 w-px bg-white/15" />
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" autoComplete="current-password" aria-label="Password"
                className="h-full min-w-0 flex-1 bg-transparent text-[0.95rem] text-[var(--heading)] outline-none sm:text-[1.15rem]" />
              <button className="pill-btn" disabled={busy || !username || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
            </div>
            {(error || notice) && <p role="alert" className={`mt-3 text-[0.85rem] ${error ? 'text-rose-300' : 'text-amber-200'}`}>{error || notice}</p>}
          </form>
        </Reveal>

        <Reveal delay={1650} className={`mt-6 max-w-[40rem] flex-col items-center gap-3 ${accounts.length ? 'flex' : 'hidden'}`}>
          <span className="text-[0.72rem] text-[var(--body-muted)] sm:text-[0.8rem]">or continue as a demo user</span>
          <div className="flex flex-wrap justify-center gap-2">
            {accounts.map((a) => (
              <button key={a.username} onClick={() => demo(a)} disabled={busy} className="pill-ghost px-3.5 py-1.5 text-[0.75rem] sm:text-[0.8rem]" title={`${a.name} - ${a.role_label}`}>
                {a.role === 'regional_manager' || a.role === 'category_manager' ? `${a.scope} manager` : a.role_label.replace(' & Logistics', '')}
              </button>
            ))}
          </div>
        </Reveal>
      </div>

      <Reveal as="footer" delay={1650} className="absolute inset-x-0 bottom-0 z-20 flex justify-center px-5 py-5 text-[0.72rem] text-[var(--body-muted)] sm:px-10 sm:py-6 sm:text-[0.8rem]">
        © 2026 Panorama — governed analytics for the whole team.
      </Reveal>
    </section>
  )
}

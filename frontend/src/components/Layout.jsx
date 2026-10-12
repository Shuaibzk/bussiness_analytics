import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { BookOpen, ChevronDown, KeyRound, LogOut, Package, Truck, Users, GitCompare } from 'lucide-react'
import { useAuth } from '../lib/auth'
import FluidBackground from './FluidBackground'
import AccountDialog from './AccountDialog'
import { Reveal, Words } from './Reveal'
import { Badge, Logo } from './ui'
import { cx } from '../lib/format'

const REPORTS = [
  { to: '/products', label: 'Products', hint: 'Sub-categories and product leaderboard', icon: Package },
  { to: '/customers', label: 'Customers', hint: 'Repeat buying, segments, top customers', icon: Users },
  { to: '/fulfilment', label: 'Fulfilment', hint: 'Delivery, returns and cancellations', icon: Truck },
  { to: '/compare', label: 'Compare', hint: 'Any two regions, years, segments...', icon: GitCompare },
]
const KEEP = ['/', '/products', '/customers', '/fulfilment', '/compare', '/orders'] // pages that share the filter query string

function Menu({ label, active, items, align = 'left', chevron = true, children }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const btn = useRef(null)
  const panel = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const down = (e) => !btn.current?.contains(e.target) && !panel.current?.contains(e.target) && setOpen(false)
    const key = (e) => { if (e.key === 'Escape') { setOpen(false); btn.current?.focus() } }
    document.addEventListener('mousedown', down)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key) }
  }, [open])
  const toggle = () => {
    const r = btn.current.getBoundingClientRect()
    setPos({ top: r.bottom + 10, left: align === 'right' ? Math.max(8, r.right - 288) : Math.max(8, Math.min(r.left, window.innerWidth - 296)) })
    setOpen(!open)
  }
  return (
    <>
      <button ref={btn} onClick={toggle} aria-haspopup="menu" aria-expanded={open}
        className={cx('relative flex items-center gap-1.5 whitespace-nowrap text-[0.95rem] transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70',
          active ? 'text-[var(--heading)]' : 'text-[var(--body-muted)] hover:text-[var(--heading)]')}>
        {label}
        {chevron && <ChevronDown size={14} className={cx('transition-transform', open && 'rotate-180')} aria-hidden="true" />}
        {active && <span className="absolute -bottom-[0.55rem] left-0 right-0 h-px bg-white/70" />}
      </button>
      {open && (
        <div ref={panel} role="menu" style={{ position: 'fixed', top: pos.top, left: pos.left, width: '18rem' }}
          className="z-50 rounded-2xl border border-white/10 bg-[#0b0d1a]/95 p-1.5 shadow-2xl backdrop-blur" onClick={() => setOpen(false)}>
          {children(items)}
        </div>
      )}
    </>
  )
}

export default function Layout() {
  const { user, meta, logout } = useAuth()
  const loc = useLocation()
  const nav = useNavigate()
  const [account, setAccount] = useState(false)
  const keep = KEEP.includes(loc.pathname) ? loc.search : ''
  const initials = user.name.split(' ').map((p) => p[0]).slice(0, 2).join('')
  const inReports = REPORTS.some((r) => loc.pathname.startsWith(r.to))

  // role-specific home: land once per session on the page that fits the role (e.g. Operations -> Fulfilment)
  useEffect(() => {
    const k = `panorama.landed.${user.id}`
    try {
      if (!sessionStorage.getItem(k)) {
        sessionStorage.setItem(k, '1')
        if (user.landing && user.landing !== '/' && loc.pathname === '/') nav(user.landing, { replace: true })
      }
    } catch { /* storage unavailable: skip */ }
  }, [user.id, user.landing]) // eslint-disable-line react-hooks/exhaustive-deps

  const link = ({ isActive }) => cx(
    'relative flex items-center gap-2 whitespace-nowrap text-[0.95rem] transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70',
    isActive ? 'text-[var(--heading)]' : 'text-[var(--body-muted)] hover:text-[var(--heading)]')
  const underline = (isActive) => isActive && <span className="absolute -bottom-[0.55rem] left-0 right-0 h-px bg-white/70" />

  return (
    <div className="print-root relative flex h-full flex-col overflow-hidden">
      <a href="#main" className="no-print sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[60] focus:rounded-full focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:text-[#2f2f33]">Skip to content</a>
      <FluidBackground variant="app" />

      <Reveal as="header" delay={150} from="-0.75rem" className="no-print relative z-20 flex shrink-0 flex-wrap items-center justify-between gap-y-3 px-5 py-5 sm:px-10 sm:py-6">
        <NavLink to="/" aria-label="Panorama home"><Logo /></NavLink>

        <nav aria-label="Main" className="glass order-3 flex h-12 w-full items-center justify-between gap-5 overflow-x-auto rounded-full px-6 lg:absolute lg:left-1/2 lg:order-none lg:w-auto lg:-translate-x-1/2 lg:justify-start lg:gap-8 lg:overflow-visible lg:px-7">
          <NavLink to={'/' + keep} end className={link}>{({ isActive }) => <>Dashboard{underline(isActive)}</>}</NavLink>
          <Menu label="Reports" active={inReports} items={REPORTS}>
            {(items) => items.map((r) => (
              <NavLink key={r.to} to={r.to + keep} role="menuitem"
                className={({ isActive }) => cx('flex items-start gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-white/10 focus-visible:bg-white/10 focus-visible:outline-none', isActive && 'bg-white/[0.07]')}>
                <r.icon size={17} className="mt-0.5 shrink-0 text-cyan-200" aria-hidden="true" />
                <span><span className="block text-[0.9rem] text-[var(--heading)]">{r.label}</span><span className="block text-[0.72rem] text-[var(--body-muted)]">{r.hint}</span></span>
              </NavLink>
            ))}
          </Menu>
          {user.features.includes('orders') && <NavLink to={'/orders' + keep} className={link}>{({ isActive }) => <>Orders{underline(isActive)}</>}</NavLink>}
          {user.features.includes('chat') && (
            <NavLink to="/analyst" className={link}>
              {({ isActive }) => <>AI Analyst
                <span className={cx('h-1.5 w-1.5 rounded-full', meta.ai.online ? (meta.ai.warm ? 'bg-emerald-400' : 'bg-sky-400 animate-pulse') : 'bg-amber-400')}
                  title={meta.ai.online ? (meta.ai.warm ? 'Local model online' : 'Local model warming up') : 'Model offline - data readout mode'} />
                {underline(isActive)}</>}
            </NavLink>
          )}
          {user.features.includes('audit') && <NavLink to="/admin" className={link}>{({ isActive }) => <>Admin{underline(isActive)}</>}</NavLink>}
        </nav>

        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2.5 xl:flex">
            <Badge tone="brand">{user.scope ? `${user.scope.value} only` : 'All data'}</Badge>
            {user.hidden_columns.includes('profit') && <Badge tone="warn">No financials</Badge>}
          </div>
          <Menu label={<span className="glass grid h-10 w-10 place-items-center rounded-full text-[0.8rem] font-medium text-[var(--heading)]" aria-label={`Account menu for ${user.name}`}>{initials}</span>} align="right" chevron={false} items={[]}>
            {() => (
              <>
                <div className="px-3 py-2"><div className="text-[0.9rem] text-[var(--heading)]">{user.name}</div><div className="text-[0.72rem] text-[var(--body-muted)]">{user.role_label}{user.scope ? ` - ${user.scope.value}` : ''}</div></div>
                <div className="hairline my-1" />
                <NavLink to="/definitions" role="menuitem" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-[0.9rem] text-[var(--heading)] hover:bg-white/10"><BookOpen size={16} aria-hidden="true" /> Data &amp; definitions</NavLink>
                <button role="menuitem" onClick={() => setAccount(true)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[0.9rem] text-[var(--heading)] hover:bg-white/10"><KeyRound size={16} aria-hidden="true" /> Change password</button>
              </>
            )}
          </Menu>
          <button onClick={logout} className="pill-btn"><LogOut size={15} aria-hidden="true" /> Sign out</button>
        </div>
      </Reveal>

      <main id="main" tabIndex={-1} className="relative z-10 min-h-0 flex-1 overflow-y-auto outline-none">
        <div className="mx-auto h-full w-full max-w-[100rem]">
          <Outlet />
        </div>
      </main>
      {account && <AccountDialog onClose={() => setAccount(false)} />}
    </div>
  )
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="px-5 pb-3 pt-4 sm:px-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[2rem] font-medium leading-[1.1] tracking-[-0.02em] text-[var(--heading)] sm:text-[2.75rem]">
            <Words text={title} delay={120} stagger={85} duration={720} y={26} />
          </h1>
          {subtitle && (
            <p className="mt-3 max-w-[48rem] text-[0.95rem] leading-normal text-[var(--body-muted)] sm:text-[1.05rem]">
              <Words text={subtitle} delay={600} stagger={22} duration={600} y={14} />
            </p>
          )}
        </div>
        {children && <Reveal delay={900}>{children}</Reveal>}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Activity, BadgeCheck, Database, EyeOff, KeyRound, MessageSquareText, ShieldAlert, ShieldCheck, ShieldX, UserPlus, Users } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAsync } from '../lib/filters'
import { PageHeader } from '../components/Layout'
import { Badge, Card, CardHeader, ErrorBox, Segmented, Skeleton } from '../components/ui'

const STATUS_TONE = { ok: 'good', denied: 'bad', error: 'warn', not_found: 'warn' }
const ROLE_TONE = { admin: 'bad', executive: 'brand', regional_manager: 'cyan', category_manager: 'good', operations: 'warn' }
const ROLES = [
  { value: 'admin', label: 'Administrator', scope: null },
  { value: 'executive', label: 'Executive', scope: null },
  { value: 'regional_manager', label: 'Regional Manager', scope: 'region' },
  { value: 'category_manager', label: 'Category Manager', scope: 'category' },
  { value: 'operations', label: 'Operations & Logistics', scope: null },
]

function Stat({ icon: Icon, label, value, sub, tone = 'text-cyan-200' }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-[var(--body-muted)]"><Icon size={14} className={tone} aria-hidden="true" /> {label}</div>
      <div className="mt-2 text-2xl font-medium">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-[var(--body-muted)]/80">{sub}</div>}
    </Card>
  )
}

const field = 'rounded-full border border-white/10 bg-white/5 px-3.5 py-2 text-[0.82rem] text-white outline-none focus:border-white/40'

function NewUserForm({ regions, categories, onDone }) {
  const [f, setF] = useState({ username: '', name: '', password: '', role: 'regional_manager', scope_value: regions[0] || '' })
  const [msg, setMsg] = useState('')
  const role = ROLES.find((r) => r.value === f.role)
  const scopes = role.scope === 'region' ? regions : role.scope === 'category' ? categories : []
  const set = (k, v) => setF((x) => ({ ...x, [k]: v, ...(k === 'role' ? { scope_value: (ROLES.find((r) => r.value === v).scope === 'region' ? regions[0] : ROLES.find((r) => r.value === v).scope === 'category' ? categories[0] : '') || '' } : {}) }))
  const submit = async (e) => {
    e.preventDefault()
    setMsg('')
    try { await api.createUser({ ...f, scope_value: role.scope ? f.scope_value : null }); setF({ ...f, username: '', name: '', password: '' }); onDone() } catch (err) { setMsg(err.message) }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3 px-6 pb-5 pt-4">
      <label className="text-[0.7rem] text-[var(--body-muted)]">Username<input className={`${field} mt-1 block w-36`} value={f.username} onChange={(e) => set('username', e.target.value)} required autoComplete="off" /></label>
      <label className="text-[0.7rem] text-[var(--body-muted)]">Full name<input className={`${field} mt-1 block w-44`} value={f.name} onChange={(e) => set('name', e.target.value)} required /></label>
      <label className="text-[0.7rem] text-[var(--body-muted)]">Role
        <select className={`${field} mt-1 block`} value={f.role} onChange={(e) => set('role', e.target.value)}>{ROLES.map((r) => <option key={r.value} value={r.value} className="bg-[#0b0d1a]">{r.label}</option>)}</select></label>
      {role.scope && <label className="text-[0.7rem] text-[var(--body-muted)]">{role.scope === 'region' ? 'Region' : 'Category'}
        <select className={`${field} mt-1 block`} value={f.scope_value} onChange={(e) => set('scope_value', e.target.value)}>{scopes.map((s) => <option key={s} className="bg-[#0b0d1a]">{s}</option>)}</select></label>}
      <label className="text-[0.7rem] text-[var(--body-muted)]">Temporary password<input type="password" className={`${field} mt-1 block w-44`} value={f.password} onChange={(e) => set('password', e.target.value)} required autoComplete="new-password" /></label>
      <button className="pill-btn !h-10"><UserPlus size={15} aria-hidden="true" /> Create user</button>
      {msg && <p role="alert" className="w-full text-[0.78rem] text-rose-300">{msg}</p>}
    </form>
  )
}

function UserRow({ u, me, regions, categories, onChange }) {
  const [edit, setEdit] = useState(false)
  const [pw, setPw] = useState(null)
  const [role, setRole] = useState(u.role)
  const [scope, setScope] = useState(u.scope_value || '')
  const [err, setErr] = useState('')
  const r = ROLES.find((x) => x.value === role)
  const scopes = r.scope === 'region' ? regions : r.scope === 'category' ? categories : []
  const run = async (fn) => { setErr(''); try { await fn(); onChange() } catch (e) { setErr(e.message) } }
  const self = u.id === me.id
  return (
    <>
      <tr className="border-b border-white/[0.04] align-middle hover:bg-white/[0.03]">
        <td className="px-4 py-2.5"><div className="font-medium text-[var(--heading)]">{u.name}</div><div className="text-[0.72rem] text-[var(--body-muted)]">{u.username}</div></td>
        <td className="px-4 py-2.5"><Badge tone={ROLE_TONE[u.role]}>{u.role_label}</Badge></td>
        <td className="px-4 py-2.5 text-[var(--body-muted)]">{u.scope_value || 'All data'}</td>
        <td className="px-4 py-2.5">{u.active ? <Badge tone="good">Active</Badge> : <Badge tone="bad">Disabled</Badge>}</td>
        <td className="px-4 py-2.5 text-right">
          <div className="flex justify-end gap-1.5">
            <button className="pill-ghost px-3 py-1 text-[0.72rem]" onClick={() => setEdit(!edit)}>Edit</button>
            <button className="pill-ghost px-3 py-1 text-[0.72rem]" onClick={() => setPw(pw === null ? '' : null)}><KeyRound size={11} aria-hidden="true" /> Reset password</button>
            <button className="pill-ghost px-3 py-1 text-[0.72rem] disabled:opacity-40" disabled={self} title={self ? 'You cannot disable yourself' : ''}
              onClick={() => run(() => api.patchUser(u.id, { active: !u.active }))}>{u.active ? 'Disable' : 'Enable'}</button>
          </div>
        </td>
      </tr>
      {(edit || pw !== null || err) && (
        <tr className="border-b border-white/[0.04] bg-white/[0.02]"><td colSpan={5} className="px-4 py-3">
          {edit && (
            <div className="flex flex-wrap items-center gap-2">
              <select className={field} value={role} disabled={self} onChange={(e) => { setRole(e.target.value); setScope('') }} aria-label="Role">{ROLES.map((x) => <option key={x.value} value={x.value} className="bg-[#0b0d1a]">{x.label}</option>)}</select>
              {r.scope && <select className={field} value={scope} onChange={(e) => setScope(e.target.value)} aria-label="Scope"><option value="" className="bg-[#0b0d1a]">Choose…</option>{scopes.map((s) => <option key={s} className="bg-[#0b0d1a]">{s}</option>)}</select>}
              <button className="pill-btn !h-9 !text-[0.78rem]" onClick={() => run(async () => { await api.patchUser(u.id, { role, scope_value: r.scope ? scope : undefined }); setEdit(false) })}>Save changes</button>
              <span className="text-[0.7rem] text-[var(--body-muted)]">Changing role or scope signs the user out immediately.</span>
            </div>
          )}
          {pw !== null && (
            <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { await api.resetPassword(u.id, pw); setPw(null) }) }}>
              <input type="password" className={field} placeholder="New temporary password" value={pw} onChange={(e) => setPw(e.target.value)} aria-label="New password" autoComplete="new-password" />
              <button className="pill-btn !h-9 !text-[0.78rem]" disabled={!pw}>Set password</button>
              <span className="text-[0.7rem] text-[var(--body-muted)]">8+ characters with letters and a digit. All of the user's sessions end.</span>
            </form>
          )}
          {err && <p role="alert" className="mt-2 text-[0.78rem] text-rose-300">{err}</p>}
        </td></tr>
      )}
    </>
  )
}

const KIND = (t) => (t.table_name.startsWith('dim_') ? 'Dimension' : t.table_name.startsWith('fact_') ? 'Fact'
  : t.table_name === 'orders' ? 'Reporting table' : t.table_type === 'VIEW' ? 'View' : 'Application')
const KIND_TONE = { Dimension: 'cyan', Fact: 'brand', 'Reporting table': 'good', View: 'neutral', Application: 'warn' }

function DatabasePanel({ state }) {
  const d = state.data
  if (state.error) return <ErrorBox error={state.error} />
  if (!d) return <Skeleton className="h-64" />
  const tot = d.constraint_totals
  const order = ['Fact', 'Dimension', 'Reporting table', 'Application', 'View']
  const tables = [...d.tables].sort((a, b) => order.indexOf(KIND(a)) - order.indexOf(KIND(b)) || a.table_name.localeCompare(b.table_name))
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat icon={Database} label="Engine" value={d.engine} sub={`${d.host} / ${d.database}`} />
        <Stat icon={Activity} label="Size" value={`${d.size_mb} MB`} sub={`${d.tables.length} tables and views`} tone="text-emerald-300" />
        <Stat icon={ShieldCheck} label="Foreign keys" value={tot['FOREIGN KEY'] ?? 0} sub="referential integrity" />
        <Stat icon={BadgeCheck} label="CHECK rules" value={tot.CHECK ?? 0} sub="enforced by the database" tone="text-amber-200" />
        <Stat icon={KeyRound} label="Migrations" value={d.migrations.length} sub="versioned, checksummed" tone="text-sky-200" />
      </div>
      <Card>
        <CardHeader title="Schema" subtitle="Star schema (one fact table, six dimensions) + a denormalised reporting table the dashboards read + application tables" />
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead><tr className="border-y border-white/[0.07] text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
              {['Table', 'Kind', 'Rows (approx)', 'Size', 'Integrity rules'].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
            <tbody>{tables.map((t) => (
              <tr key={t.table_name} className="border-b border-white/[0.04] hover:bg-white/[0.03]">
                <td className="px-4 py-2 font-mono text-[0.8rem] text-[var(--heading)]">{t.table_name}</td>
                <td className="px-4 py-2"><Badge tone={KIND_TONE[KIND(t)]}>{KIND(t)}</Badge></td>
                <td className="px-4 py-2 tabular-nums text-[var(--body-muted)]">{t.table_type === 'VIEW' ? '-' : t.approx_rows.toLocaleString()}</td>
                <td className="px-4 py-2 tabular-nums text-[var(--body-muted)]">{t.table_type === 'VIEW' ? '-' : `${t.size_mb} MB`}</td>
                <td className="px-4 py-2"><div className="flex flex-wrap gap-1">
                  {Object.entries(t.constraints).map(([k, n]) => <Badge key={k}>{n} {k.toLowerCase()}</Badge>)}
                  {!Object.keys(t.constraints).length && <span className="text-[var(--body-muted)]/60">-</span>}
                </div></td>
              </tr>))}</tbody>
          </table>
        </div>
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Least privilege" subtitle="What the web application's database account may do (SHOW GRANTS)" />
          <div className="space-y-1.5 px-6 pb-5 pt-4">
            {d.app_account_grants.map((g) => <pre key={g} className="overflow-x-auto rounded-xl bg-black/30 px-3 py-1.5 font-mono text-[11px] text-emerald-300/90">{g}</pre>)}
            <p className="pt-1 text-[0.72rem] text-[var(--body-muted)]">No DROP, ALTER or CREATE. No direct access to fact or dimension tables. audit_log is insert + select only, so the app cannot edit its own history.</p>
          </div>
        </Card>
        <Card>
          <CardHeader title="Migrations" subtitle="Applied in order; editing an applied file is detected by its checksum" />
          <ul className="space-y-2 px-6 pb-5 pt-4 text-[0.85rem]">
            {d.migrations.map((m) => (
              <li key={m.version} className="flex items-center justify-between gap-3"><span className="font-mono text-[0.78rem] text-[var(--heading)]">{m.name}</span><span className="text-[0.72rem] text-[var(--body-muted)]">{m.applied_at}</span></li>))}
          </ul>
        </Card>
      </div>
    </div>
  )
}

export default function Admin() {
  const { user, meta } = useAuth()
  const [tab, setTab] = useState('access')
  const [filter, setFilter] = useState('all')
  const [tick, setTick] = useState(0)
  const sys = useAsync(() => api.system(), [tick, tab])
  const users = useAsync(() => api.users(), [tick])
  const audit = useAsync(() => api.audit(), [tab, tick])
  const dbo = useAsync(() => (tab === 'database' ? api.database() : Promise.resolve(null)), [tab])
  const chain = useAsync(() => api.verifyAudit(), [tab, tick])

  const regions = meta.options.dims.region?.values || []
  const categories = meta.options.dims.category?.values || []
  const roles = {}
  users.data?.forEach((u) => { (roles[u.role] ||= { ...u, members: [] }).members.push(u) })
  const rows = (audit.data?.rows || []).filter((r) => filter === 'all' || r.status === filter)
  const fb = sys.data?.feedback

  return (
    <div className="pb-10">
      <PageHeader title="Administration" subtitle="Users, access policy, system health and a tamper-evident audit trail" />
      <div className="space-y-5 px-5 pt-3 sm:px-10">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Stat icon={Database} label="Orders in database" value={sys.data?.orders?.toLocaleString() ?? '-'} sub={sys.data ? `${sys.data.db_engine} - ${sys.data.db_mb} MB` : ''} />
          <Stat icon={Activity} label="Query cache hit rate" value={sys.data ? `${sys.data.cache.hit_rate}%` : '-'} sub={sys.data ? `${sys.data.cache.hits} hits - ${sys.data.cache.misses} misses` : ''} tone="text-emerald-300" />
          <Stat icon={KeyRound} label="Knowledge base" value={sys.data ? `${sys.data.rag.documents} docs` : '-'} sub={sys.data?.llm?.warm ? `${sys.data.llm.chat_model} warm` : sys.data?.rag.dense ? 'BM25 + embeddings' : 'BM25 keyword index'} />
          <Stat icon={Users} label="Active sessions" value={sys.data?.active_sessions ?? '-'} sub="signed in within the idle window" tone="text-sky-200" />
          <Stat icon={MessageSquareText} label="Answer feedback" value={fb ? `${fb.helpful} / ${fb.not_helpful}` : '-'} sub={fb ? `helpful / not helpful of ${fb.answers} answers` : ''} tone="text-amber-200" />
        </div>

        <Segmented size="md" label="Admin sections" value={tab} onChange={setTab} options={[{ value: 'access', label: 'Access policy' }, { value: 'users', label: 'Users' }, { value: 'database', label: 'Database' }, { value: 'audit', label: 'Audit log' }]} />

        {tab === 'access' && (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {users.error && <ErrorBox error={users.error} />}
            {Object.values(roles).map((r, i) => (
              <Card key={r.role} delay={i * 0.05} className="p-5">
                <div className="flex items-center justify-between">
                  <Badge tone={ROLE_TONE[r.role]}>{r.role_label}</Badge>
                  <span className="text-xs text-[var(--body-muted)]/70">{r.members.length} user{r.members.length > 1 ? 's' : ''}</span>
                </div>
                <div className="mt-4 space-y-3 text-sm">
                  <div>
                    <div className="mb-1 flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-[var(--body-muted)]/70"><ShieldCheck size={12} aria-hidden="true" /> Rows</div>
                    <div className="text-[var(--heading)]">{r.role === 'regional_manager' ? 'Only their own region' : r.role === 'category_manager' ? 'Only their own category' : 'All rows'}</div>
                  </div>
                  <div>
                    <div className="mb-1 flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-[var(--body-muted)]/70"><EyeOff size={12} aria-hidden="true" /> Hidden columns</div>
                    <div className="flex flex-wrap gap-1">{r.hidden_columns.length ? r.hidden_columns.map((c) => <Badge key={c} tone="bad">{c}</Badge>) : <span className="text-[var(--body-muted)]">None</span>}</div>
                  </div>
                  <div>
                    <div className="mb-1 text-[11px] uppercase tracking-wider text-[var(--body-muted)]/70">Features</div>
                    <div className="flex flex-wrap gap-1">{r.features.map((f) => <Badge key={f} tone="neutral">{f}</Badge>)}</div>
                  </div>
                  <div>
                    <div className="mb-1 text-[11px] uppercase tracking-wider text-[var(--body-muted)]/70">Members</div>
                    <div className="space-y-0.5 text-xs text-[var(--body-muted)]">{r.members.map((m) => <div key={m.id}>{m.name} <span className="text-[var(--body-muted)]/60">- {m.username}{m.scope_value ? ` (${m.scope_value})` : ''}</span></div>)}</div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {tab === 'users' && (
          <Card>
            <CardHeader title="User management" subtitle="Create accounts, change roles and scopes, reset passwords, disable access. Every change is audited and takes effect immediately." />
            <NewUserForm regions={regions} categories={categories} onDone={() => setTick((t) => t + 1)} />
            <div className="hairline" />
            <div className="overflow-x-auto">
              {users.loading && !users.data ? <div className="p-5"><Skeleton className="h-40" /></div> : (
                <table className="w-full min-w-[760px] text-sm">
                  <thead><tr className="border-b border-white/[0.07] text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
                    {['User', 'Role', 'Scope', 'Status', ''].map((h) => <th key={h} scope="col" className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
                  <tbody>{(users.data || []).map((u) => <UserRow key={u.id} u={u} me={user} regions={regions} categories={categories} onChange={() => setTick((t) => t + 1)} />)}</tbody>
                </table>
              )}
            </div>
          </Card>
        )}

        {tab === 'database' && <DatabasePanel state={dbo} />}

        {tab === 'audit' && (
          <Card>
            <CardHeader title="Audit log" subtitle="Every login, chat question, export, user change and denied attempt - each entry is hash-chained to the previous one"
              right={<div className="flex flex-wrap items-center justify-end gap-2">
                {chain.data && (chain.data.ok
                  ? <Badge tone="good"><BadgeCheck size={12} aria-hidden="true" /> Chain intact - {chain.data.entries} entries</Badge>
                  : <Badge tone="bad"><ShieldAlert size={12} aria-hidden="true" /> Tampering detected at entry #{chain.data.broken_at}</Badge>)}
                <Segmented label="Filter by status" value={filter} onChange={setFilter} options={[{ value: 'all', label: 'All' }, { value: 'ok', label: 'OK' }, { value: 'denied', label: 'Denied' }]} />
              </div>} />
            <div className="mt-3 overflow-x-auto">
              {audit.loading && !audit.data ? <div className="p-5"><Skeleton className="h-40" /></div> : (
                <table className="w-full min-w-[800px] text-xs">
                  <thead><tr className="border-y border-white/[0.07] text-left text-[11px] uppercase tracking-wider text-[var(--body-muted)]">
                    {['Time (UTC)', 'User', 'Role', 'Scope', 'Action', 'Status', 'Detail'].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} className="border-b border-white/[0.04] align-top hover:bg-white/[0.03]">
                        <td className="whitespace-nowrap px-4 py-2 text-[var(--body-muted)]">{r.ts}</td>
                        <td className="px-4 py-2 font-medium text-[var(--heading)]">{r.username}</td>
                        <td className="px-4 py-2 text-[var(--body-muted)]">{r.role || '-'}</td>
                        <td className="px-4 py-2 text-[var(--body-muted)]">{r.scope || '-'}</td>
                        <td className="px-4 py-2 text-[var(--heading)]">{r.action}</td>
                        <td className="px-4 py-2"><Badge tone={STATUS_TONE[r.status] || 'neutral'}>{r.status}</Badge></td>
                        <td className="max-w-md truncate px-4 py-2 font-mono text-[11px] text-[var(--body-muted)]/80" title={r.detail}>{r.detail}</td>
                      </tr>
                    ))}
                    {!rows.length && <tr><td colSpan={7} className="p-8 text-center text-[var(--body-muted)]">No entries yet</td></tr>}
                  </tbody>
                </table>
              )}
            </div>
          </Card>
        )}
        {sys.data && <p className="flex items-center gap-2 text-[0.7rem] text-[var(--body-muted)]/70"><ShieldX size={12} aria-hidden="true" /> Sessions are httpOnly cookies, revocable server-side, with a {meta.session?.idle_minutes}-minute idle timeout. Chat contents are private to each user and are not shown here.</p>}
      </div>
    </div>
  )
}

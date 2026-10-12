import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Bot, Check, ChevronDown, Code2, Copy, Database, FileText, RotateCcw, Send, ShieldAlert, Sparkles, Square, ThumbsDown, ThumbsUp, Trash2, User as UserIcon } from 'lucide-react'
import { api, downloadCsv, streamChat } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dimLabel, fmt, PALETTE } from '../lib/format'
import { PageHeader } from '../components/Layout'
import { Badge } from '../components/ui'
import { ColBars, TrendChart } from '../components/charts'

/** minimal markdown: **bold**, _italic_, "- " bullets, paragraphs */
function Md({ text }) {
  const inline = (s) => s.split(/(\*\*[^*]+\*\*|_[^_]+_)/g).map((p, i) =>
    p.startsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong> : p.startsWith('_') && p.endsWith('_') && p.length > 2 ? <em key={i}>{p.slice(1, -1)}</em> : p)
  const blocks = text.split(/\n{2,}/)
  return blocks.map((b, i) => {
    const lines = b.split('\n')
    if (lines.every((l) => /^\s*[-*] /.test(l))) return <ul key={i}>{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*[-*] /, ''))}</li>)}</ul>
    return <p key={i}>{lines.map((l, j) => <span key={j}>{inline(l)}{j < lines.length - 1 && <br />}</span>)}</p>
  })
}

const plain = (s) => s.replace(/\*\*/g, '').replace(/(^|\s)_([^_]+)_/g, '$1$2')

function MiniTable({ table }) {
  const cols = table.columns
  const cell = (c, v) => (c.role === 'dimension' ? dimLabel(c.key, v) : fmt(c.fmt, v))
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10">
      <div className="flex items-center justify-end border-b border-white/[0.06] px-2 py-1">
        <button onClick={() => downloadCsv('panorama_chat_result.csv', cols.map((c) => c.label), table.rows.map((r) => r.map((v, j) => cell(cols[j], v))))}
          className="rounded-full px-2.5 py-1 text-[11px] text-[var(--body-muted)] hover:bg-white/10 hover:text-white" aria-label="Download this table as CSV">Download CSV</button>
      </div>
      <table className="w-full text-xs">
        <thead><tr className="bg-white/5 text-left text-[10px] uppercase tracking-wider text-[var(--body-muted)]">
          {cols.map((c) => <th key={c.key} scope="col" className="px-3 py-2 font-medium">{c.label}</th>)}</tr></thead>
        <tbody>
          {table.rows.slice(0, 12).map((r, i) => (
            <tr key={i} className="border-t border-white/[0.06]">
              {r.map((v, j) => <td key={j} className={`px-3 py-1.5 ${cols[j].role === 'metric' ? 'tabular-nums text-white' : 'text-[var(--body-muted)]'}`}>{cell(cols[j], v)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {table.rows.length > 12 && <div className="border-t border-white/[0.06] px-3 py-1.5 text-[11px] text-[var(--body-muted)]/70">+ {table.rows.length - 12} more rows (download for all)</div>}
    </div>
  )
}

function InlineChart({ chart }) {
  const data = chart.labels.map((l, i) => Object.fromEntries([['x', l], ...chart.series.map((s, k) => [`s${k}`, s.data[i]])]))
  const series = chart.series.map((s, k) => ({ key: `s${k}`, name: s.name, fmt: s.fmt, color: PALETTE[k % PALETTE.length] }))
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-2">
      {chart.type === 'line'
        ? <TrendChart data={data} series={series} kind="area" height={190} />
        : <ColBars data={data} series={series} fmtKind={series[0].fmt} height={190} />}
    </div>
  )
}

function Sources({ msg }) {
  const [open, setOpen] = useState(false)
  const m = msg.meta
  if (!m || m.denied) return null
  const done = msg.done || m.done
  return (
    <div className="mt-3">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--body-muted)] hover:text-white">
        <Code2 size={12} aria-hidden="true" /> How I got this
        <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
        {done && <span className="ml-2 font-normal text-[var(--body-muted)]/70">{(done.ms / 1000).toFixed(1)}s{done.mode === 'fallback' ? ' - model offline' : ''}</span>}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mt-2 space-y-2 rounded-2xl border border-white/10 bg-black/25 p-3 text-xs">
              {m.plan && <div className="flex flex-wrap gap-1.5">
                <Badge tone="brand">plan: {m.plan_source}</Badge>
                {m.plan.metrics?.map((x) => <Badge key={x} tone="good">{x}</Badge>)}
                {m.plan.group_by?.map((x) => <Badge key={x} tone="cyan">by {x}</Badge>)}
                {Object.entries(m.plan.filters || {}).map(([k, v]) => <Badge key={k} tone="warn">{k}: {[].concat(v).join(', ')}</Badge>)}
                {m.plan.lookup && <Badge tone="cyan">record lookup {m.plan.lookup}</Badge>}
                <Badge>{m.plan.basis}</Badge>
              </div>}
              {m.sql && <pre className="overflow-x-auto rounded-xl bg-black/40 p-2.5 font-mono text-[11px] leading-relaxed text-emerald-300/90">{m.sql}</pre>}
              {(m.sources || []).map((s, i) => (
                <div key={i} className="flex gap-2 text-[var(--body-muted)]">
                  {s.type === 'query' ? <Database size={13} className="mt-0.5 shrink-0 text-emerald-300" aria-hidden="true" /> : <FileText size={13} className="mt-0.5 shrink-0 text-cyan-200" aria-hidden="true" />}
                  <div className="min-w-0"><div className="font-medium text-[var(--heading)]">{s.title}</div>{s.detail && <div className="text-[var(--body-muted)]/70">{s.detail}</div>}</div>
                </div>
              ))}
              {done?.timings && Object.keys(done.timings).length > 0 && <div className="text-[11px] text-[var(--body-muted)]/70">plan {done.timings.plan_ms}ms - query {done.timings.query_ms}ms - retrieval {done.timings.retrieve_ms}ms - generation {done.timings.generate_ms}ms</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Actions({ msg, onRate, onRegenerate }) {
  const [copied, setCopied] = useState(false)
  if (msg.streaming || !msg.content) return null
  const btn = 'grid h-7 w-7 place-items-center rounded-full text-[var(--body-muted)] transition-colors hover:bg-white/10 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/70'
  return (
    <div className="mt-2 flex items-center gap-0.5" role="group" aria-label="Answer actions">
      <button className={btn} title="Copy answer" aria-label="Copy answer" onClick={async () => { try { await navigator.clipboard.writeText(plain(msg.content)); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* clipboard blocked */ } }}>
        {copied ? <Check size={14} className="text-emerald-300" /> : <Copy size={14} />}
      </button>
      <button className={btn} title="Ask again" aria-label="Regenerate answer" onClick={onRegenerate}><RotateCcw size={14} /></button>
      {msg.id && (
        <>
          <button className={`${btn} ${msg.rating === 1 ? '!text-emerald-300' : ''}`} title="Helpful" aria-label="Mark answer as helpful" aria-pressed={msg.rating === 1} onClick={() => onRate(msg, msg.rating === 1 ? 0 : 1)}><ThumbsUp size={14} /></button>
          <button className={`${btn} ${msg.rating === -1 ? '!text-rose-300' : ''}`} title="Not helpful" aria-label="Mark answer as not helpful" aria-pressed={msg.rating === -1} onClick={() => onRate(msg, msg.rating === -1 ? 0 : -1)}><ThumbsDown size={14} /></button>
        </>
      )}
    </div>
  )
}

function Message({ msg, onRate, onRegenerate }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[80%] rounded-[1.4rem] rounded-tr-md bg-white px-4 py-2.5 text-sm text-[var(--action-inverse-fg)]">{msg.content}</div>
        <div className="glass grid h-8 w-8 shrink-0 place-items-center rounded-full" aria-hidden="true"><UserIcon size={15} /></div>
      </div>
    )
  }
  const denied = msg.meta?.denied
  return (
    <div className="flex gap-3">
      <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${denied ? 'bg-amber-400/15 text-amber-300' : 'glass text-white'}`} aria-hidden="true">
        {denied ? <ShieldAlert size={15} /> : <Bot size={16} />}
      </div>
      <div className="min-w-0 max-w-[88%] flex-1 space-y-3">
        <div className={`glass rounded-[1.4rem] rounded-tl-md px-4 py-3 text-sm leading-relaxed ${denied ? '!border-amber-400/25' : ''}`}>
          <div className={`prose-chat ${msg.streaming ? 'caret' : ''}`}>{msg.content ? <Md text={msg.content} /> : <span className="text-[var(--body-muted)]/70">Analysing the data...</span>}</div>
          <Sources msg={msg} />
          <Actions msg={msg} onRate={onRate} onRegenerate={onRegenerate} />
        </div>
        {msg.meta?.chart && <InlineChart chart={msg.meta.chart} />}
        {msg.meta?.table && msg.meta.table.rows.length > 0 && <MiniTable table={msg.meta.table} />}
      </div>
    </div>
  )
}

export default function Analyst() {
  const { meta, user } = useAuth()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const endRef = useRef(null)
  const abortRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    api.chatHistory().then((h) => setMessages(h.map((m) => ({ ...m, done: m.meta?.done })))).catch(() => {}).finally(() => setLoaded(true))
  }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages])

  const ask = async (question) => {
    const text = (question ?? input).trim()
    if (!text || busy) return
    setInput('')
    // the previous query's plan travels with the history so follow-ups ("and in Europe?") can build on it
    const history = messages.filter((m) => m.content).map((m) => ({ role: m.role, content: m.content, plan: m.meta?.plan }))
    setMessages((m) => [...m, { role: 'user', content: text }, { role: 'assistant', content: '', streaming: true }])
    setBusy(true)
    const ctl = new AbortController()
    abortRef.current = ctl
    const patch = (fn) => setMessages((all) => { const c = [...all]; c[c.length - 1] = fn(c[c.length - 1]); return c })
    try {
      await streamChat(text, history, {
        meta: (m) => patch((x) => ({ ...x, meta: m })),
        token: (t) => patch((x) => ({ ...x, content: x.content + t })),
        done: (d) => patch((x) => ({ ...x, done: d, streaming: false })),
        saved: (s) => patch((x) => ({ ...x, id: s.id })),
      }, ctl.signal)
    } catch (e) {
      patch((x) => ({ ...x, streaming: false, content: x.content || (e.name === 'AbortError' ? '_Stopped._' : `Sorry - ${e.message}`) }))
    } finally {
      patch((x) => ({ ...x, streaming: false }))
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  const rate = async (msg, rating) => {
    setMessages((all) => all.map((m) => (m.id === msg.id ? { ...m, rating: rating || null } : m)))
    try { await api.feedback(msg.id, rating) } catch { /* optimistic; ignore */ }
  }
  const regenerate = (idx) => {
    const q = [...messages].slice(0, idx).reverse().find((m) => m.role === 'user')
    if (q) ask(q.content)
  }
  const clear = async () => { await api.clearChat(); setMessages([]) }
  const warming = meta.ai.online && !meta.ai.warm

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="AI Analyst" subtitle="Ask questions in plain English. Answers are grounded in your governed data and knowledge base.">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={meta.ai.online ? 'good' : 'warn'}><span className={`h-1.5 w-1.5 rounded-full ${meta.ai.online ? (warming ? 'animate-pulse bg-sky-400' : 'bg-emerald-400') : 'bg-amber-400'}`} />
            {meta.ai.online ? (warming ? `${meta.ai.model} warming up` : `${meta.ai.model} (local)`) : 'Language model offline - data readout mode'}</Badge>
          <Badge tone="brand">{meta.ai.dense_retrieval ? 'Hybrid retrieval: BM25 + embeddings' : 'Keyword retrieval (BM25)'}</Badge>
          <Badge>{user.scope ? `Scope: ${user.scope.value}` : 'Scope: all data'}</Badge>
          {messages.length > 0 && <button onClick={clear} className="pill-ghost px-3 py-1 text-[0.72rem]" aria-label="Clear conversation"><Trash2 size={12} aria-hidden="true" /> Clear</button>}
        </div>
      </PageHeader>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-10" role="log" aria-live="polite" aria-label="Conversation">
        <div className="mx-auto max-w-3xl space-y-5">
          {warming && <p className="text-center text-[0.75rem] text-sky-200/80">The language model is still loading into memory - the first answer can take up to a minute.</p>}
          {loaded && !messages.length && (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="pt-10 text-center">
              <div className="glass mx-auto mb-6 grid h-16 w-16 place-items-center rounded-full text-white" aria-hidden="true"><Sparkles size={26} /></div>
              <h2 className="text-[2rem] font-medium">What would you like to know?</h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-[var(--body-muted)]">Try one of these, tailored to your role. You can follow up ("and in Europe?") or look up a record (ORD-000004). Every answer shows the query and sources it used.</p>
              <div className="mx-auto mt-6 grid max-w-2xl gap-2 sm:grid-cols-2">
                {meta.suggestions.map((s, i) => (
                  <motion.button key={s} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.05 }} onClick={() => ask(s)}
                    className="glass rounded-[1.25rem] px-5 py-3.5 text-left text-sm text-[var(--heading)] transition-colors hover:border-white/30 hover:bg-white/[0.07]">{s}</motion.button>
                ))}
              </div>
            </motion.div>
          )}
          {messages.map((m, i) => <Message key={m.id ? `m${m.id}-${i}` : `t${i}`} msg={m} onRate={rate} onRegenerate={() => regenerate(i)} />)}
          <div ref={endRef} />
        </div>
      </div>

      <div className="px-5 pb-6 pt-3 sm:px-10">
        <form onSubmit={(e) => { e.preventDefault(); ask() }} className="mx-auto flex max-w-3xl items-center gap-2">
          <div className="glass flex flex-1 items-center rounded-full px-5 py-1 focus-within:border-white/40">
            <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about revenue, returns, shipping, customers, or an order id..." maxLength={600} aria-label="Your question"
              className="w-full bg-transparent py-3 text-sm outline-none placeholder:text-[var(--body-muted)]" />
          </div>
          {busy
            ? <button type="button" onClick={() => abortRef.current?.abort()} className="glass grid h-12 w-12 place-items-center rounded-full" aria-label="Stop answering"><Square size={16} /></button>
            : <button disabled={!input.trim()} className="pill-btn !h-12 !w-12 !p-0" aria-label="Send question"><Send size={17} /></button>}
        </form>
      </div>
    </div>
  )
}

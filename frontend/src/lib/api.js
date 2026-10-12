
const CSRF = { 'X-Requested-With': 'panorama' }

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => (onUnauthorized = fn)

async function request(path, { method = 'GET', body, raw = false, quiet401 = false } = {}) {
  const headers = { ...CSRF }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(`/api${path}`, { method, headers, credentials: 'same-origin', body: body !== undefined ? JSON.stringify(body) : undefined })
  if (res.status === 401 && !quiet401) onUnauthorized()
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* ignore */ }
    const err = new Error(typeof detail === 'string' ? detail : 'Request failed')
    err.status = res.status
    throw err
  }
  return raw ? res : res.json()
}

export const api = {
  login: (username, password) => request('/auth/login', { method: 'POST', body: { username, password }, quiet401: true }),
  logout: () => request('/auth/logout', { method: 'POST', quiet401: true }).catch(() => {}),
  changePassword: (current_password, new_password) => request('/auth/change-password', { method: 'POST', body: { current_password, new_password } }),
  demoAccounts: () => request('/auth/demo-accounts', { quiet401: true }),
  meta: (quiet = false) => request('/meta', { quiet401: quiet }),
  query: (body) => request('/query', { method: 'POST', body }),
  kpis: (body) => request('/kpis', { method: 'POST', body }),
  insights: (body) => request('/insights', { method: 'POST', body }),
  customers: (body) => request('/customers', { method: 'POST', body }),
  forecast: (body) => request('/forecast', { method: 'POST', body }),
  targets: () => request('/targets'),
  setTarget: (metric, year, value) => request('/targets', { method: 'PUT', body: { metric, year, value } }),
  deleteTarget: (metric, year) => request(`/targets/${metric}/${year}`, { method: 'DELETE' }),
  orders: (body) => request('/orders', { method: 'POST', body }),
  exportOrders: async (body) => {
    const res = await request('/orders/export', { method: 'POST', body, raw: true })
    saveBlob(await res.blob(), 'panorama_orders.csv')
  },
  exportEvent: (what, rows) => request('/export-event', { method: 'POST', body: { what, rows } }).catch(() => {}),
  chatHistory: () => request('/chat/history'),
  clearChat: () => request('/chat/history', { method: 'DELETE' }),
  feedback: (message_id, rating) => request('/chat/feedback', { method: 'POST', body: { message_id, rating } }),
  audit: () => request('/admin/audit?limit=300'),
  verifyAudit: () => request('/admin/audit/verify'),
  database: () => request('/admin/database'),
  users: () => request('/admin/users'),
  createUser: (body) => request('/admin/users', { method: 'POST', body }),
  patchUser: (id, body) => request(`/admin/users/${id}`, { method: 'PATCH', body }),
  resetPassword: (id, password) => request(`/admin/users/${id}/reset-password`, { method: 'POST', body: { password } }),
  system: () => request('/admin/system'),
}

export function saveBlob(blob, filename) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

/** Client-side CSV of data the user is already viewing (chart/table download). Cells are quoted; formulas are neutralised. */
export function toCsv(columns, rows) {
  const cell = (v) => {
    let s = v == null ? '' : String(v)
    if (/^[=+\-@]/.test(s) && Number.isNaN(Number(s))) s = `'${s}` // CSV-injection guard for spreadsheet apps
    return `"${s.replace(/"/g, '""')}"`
  }
  return [columns.map(cell).join(','), ...rows.map((r) => r.map(cell).join(','))].join('\r\n')
}

export function downloadCsv(filename, columns, rows) {
  saveBlob(new Blob(['﻿' + toCsv(columns, rows)], { type: 'text/csv;charset=utf-8' }), filename)
  api.exportEvent(filename, rows.length)
}

/** Streams the chat answer over SSE. handlers: { meta, token, done, saved } */
export async function streamChat(question, history, handlers, signal) {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    signal,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...CSRF },
    body: JSON.stringify({ question, history }),
  })
  if (res.status === 401) onUnauthorized()
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const block = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const ev = /event: (\w+)/.exec(block)?.[1]
      const data = /data: (.*)/s.exec(block)?.[1]
      if (ev && data !== undefined) handlers[ev]?.(JSON.parse(data))
    }
  }
}

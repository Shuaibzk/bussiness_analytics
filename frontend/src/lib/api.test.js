import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, setUnauthorizedHandler, toCsv } from './api'

describe('toCsv', () => {
  it('quotes cells and escapes embedded quotes', () => {
    expect(toCsv(['Name', 'Note'], [['Ann', 'say "hi"']])).toBe('"Name","Note"\r\n"Ann","say ""hi"""')
  })
  it('neutralises spreadsheet formulas (CSV injection)', () => {
    const csv = toCsv(['x'], [['=HYPERLINK("http://evil")'], ['+SUM(A1)'], ['@cmd'], ['-5'], ['normal']])
    expect(csv).toContain(`"'=HYPERLINK`)
    expect(csv).toContain(`"'+SUM(A1)"`)
    expect(csv).toContain(`"'@cmd"`)
    expect(csv).toContain('"-5"') // genuine negative numbers are left alone
    expect(csv).toContain('"normal"')
  })
  it('turns null/undefined into empty cells', () => {
    expect(toCsv(['a', 'b'], [[null, undefined]])).toBe('"a","b"\r\n"",""')
  })
})

describe('api client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends the CSRF header and same-origin credentials, and never attaches a bearer token', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    await api.kpis({ filters: {}, basis: 'net' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/kpis')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(init.headers['X-Requested-With']).toBe('panorama')
    expect(init.headers.Authorization).toBeUndefined()
  })

  it('calls the unauthorized handler on 401 (session ended)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Session timed out' }), { status: 401 }))
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    await expect(api.meta()).rejects.toThrow('Session timed out')
    expect(handler).toHaveBeenCalledOnce()
  })

  it('does not trigger the handler for a failed login (401 is expected there)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Invalid username or password' }), { status: 401 }))
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    await expect(api.login('a', 'b')).rejects.toThrow('Invalid username or password')
    expect(handler).not.toHaveBeenCalled()
  })

  it('surfaces the server error message and status', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Your role cannot access revenue' }), { status: 403 }))
    setUnauthorizedHandler(() => {})
    await expect(api.query({ metrics: ['revenue'] })).rejects.toMatchObject({ message: 'Your role cannot access revenue', status: 403 })
  })
})

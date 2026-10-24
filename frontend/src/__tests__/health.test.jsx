import { act, renderHook } from '@testing-library/react'
import { vi } from 'vitest'
import { useHealth } from '../hooks.js'

// The header's status light asks two questions: /health (is the API up? cheap, asked often) and /health/db (is the
// database up? it wakes a sleeping database, so it is asked rarely). These tests use fake time to check HOW OFTEN.

// Simple pretend answers that are ready at once. (A real Response reads its body through the event loop, which the
// fake clock cannot move forward, so these tests use plain objects with the same ok / status / json() shape.)
const reply = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })
const API = () => reply({ status: 'ok' })
const DB_OK = () => reply({ status: 'ok', database: 'reachable' })
const DB_DOWN = () => reply({ detail: 'Database unavailable' }, 503)

// A pretend server whose answers can be changed during a test.
function server(overrides = {}) {
  const answers = { '/health': API, '/health/db': DB_OK, ...overrides }
  const fetchMock = vi.fn(async (url) => {
    const result = answers[url]()
    if (result instanceof Error) throw result
    return result
  })
  vi.stubGlobal('fetch', fetchMock)
  return {
    fetchMock,
    set: (path, answer) => { answers[path] = answer },
    calls: (path) => fetchMock.mock.calls.filter(([url]) => url === path).length,
  }
}

// moves the fake clock AND lets the pending answers arrive; act() lets React show the new status
const tick = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  delete document.hidden // remove a fake "tab is hidden" set by a test, so the real value shows again
})

describe('the header status light: what it asks, and how often', () => {
  it('asks both routes at the start, and says OK when both answer', async () => {
    const api = server()
    const { result } = renderHook(() => useHealth(15000, 60000))
    expect(result.current.status).toBe('checking')
    await tick(10)
    expect(result.current.status).toBe('ok')
    expect(api.calls('/health')).toBe(1)
    expect(api.calls('/health/db')).toBe(1)
  })

  it('asks /health every 15 seconds but does NOT wake the database each time', async () => {
    const api = server()
    renderHook(() => useHealth(15000, 60000))
    await tick(10)
    await tick(45000) // three more 15-second ticks
    expect(api.calls('/health')).toBe(4)
    expect(api.calls('/health/db')).toBe(1) // still only the first one
  })

  it('checks the database again once a minute has passed', async () => {
    const api = server()
    renderHook(() => useHealth(15000, 60000))
    await tick(10)
    await tick(60000)
    expect(api.calls('/health/db')).toBe(2)
  })

  it('never asks the database while the browser tab is hidden', async () => {
    const api = server()
    renderHook(() => useHealth(15000, 60000))
    await tick(10)
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    await tick(5 * 60000)
    expect(api.calls('/health/db')).toBe(1) // five minutes later, still only the first
    expect(api.calls('/health')).toBeGreaterThan(10) // the cheap check carries on
  })

  it('says the database is down when /health/db answers 503, while the API is still up', async () => {
    server({ '/health/db': DB_DOWN })
    const { result } = renderHook(() => useHealth(15000, 60000))
    await tick(10)
    expect(result.current.status).toBe('db-down')
  })

  it('recovers to OK at the next database check', async () => {
    const api = server({ '/health/db': DB_DOWN })
    const { result } = renderHook(() => useHealth(15000, 60000))
    await tick(10)
    expect(result.current.status).toBe('db-down')
    api.set('/health/db', DB_OK)
    await tick(60000)
    expect(result.current.status).toBe('ok')
  })

  it('says the API is unreachable when /health does not answer, and does not ask about the database', async () => {
    const api = server()
    api.set('/health', () => new TypeError('Failed to fetch'))
    const { result } = renderHook(() => useHealth(15000, 60000))
    await tick(10)
    expect(result.current.status).toBe('api-down')
    expect(api.calls('/health/db')).toBe(0)
  })

  it('checks the database straight away when the API comes back, instead of waiting a minute', async () => {
    const api = server()
    const { result } = renderHook(() => useHealth(15000, 60000))
    await tick(10)
    api.set('/health', () => new TypeError('Failed to fetch'))
    await tick(15000)
    expect(result.current.status).toBe('api-down')
    api.set('/health', API)
    api.set('/health/db', DB_DOWN) // and the database turned out to be down while the API was away
    await tick(15000) // well under a minute after the last database check
    expect(api.calls('/health/db')).toBe(2)
    expect(result.current.status).toBe('db-down')
  })

  it('treats an unexpected HTTP error from /health as "unexpected", not as a database problem', async () => {
    const api = server()
    api.set('/health', () => reply({ detail: 'Bad Gateway' }, 502))
    const { result } = renderHook(() => useHealth(15000, 60000))
    await tick(10)
    expect(result.current.status).toBe('error')
    expect(api.calls('/health/db')).toBe(0)
  })
})

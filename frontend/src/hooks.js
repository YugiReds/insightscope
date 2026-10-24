import { useCallback, useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import { ApiError, getJson } from './api.js'

// The date range chosen under "Why drugs are recalled". It lives here (not inside that section) so the "Download
// report" buttons and the printed page can follow the same range.
export function useDateRange() {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const error = from && to && from > to ? 'The "From" date must be on or before the "To" date.' : null
  return { from, to, setFrom, setTo, error }
}

// True while the browser is printing (from just before the print layout is made until printing ends). Charts use it to
// switch to a fixed width, because a stretchy chart cannot be trusted to resize itself in time for paper.
export function usePrinting() {
  const [printing, setPrinting] = useState(false)
  useEffect(() => {
    const start = () => flushSync(() => setPrinting(true)) // flushSync: finish updating the page BEFORE printing starts
    const end = () => flushSync(() => setPrinting(false))
    window.addEventListener('beforeprint', start)
    window.addEventListener('afterprint', end)
    return () => {
      window.removeEventListener('beforeprint', start)
      window.removeEventListener('afterprint', end)
    }
  }, [])
  return printing
}

// The date and time shown on the printed report. It is refreshed just before printing, so a page that has been
// open for hours still prints the moment it was printed.
export function useGeneratedAt() {
  const [generatedAt, setGeneratedAt] = useState(() => new Date())
  useEffect(() => {
    const refresh = () => flushSync(() => setGeneratedAt(new Date())) // flushSync: update the page BEFORE printing starts
    window.addEventListener('beforeprint', refresh)
    return () => window.removeEventListener('beforeprint', refresh)
  }, [])
  return generatedAt
}

// Loads one API path and reports { data, error, loading, reload }.
// While it reloads (a new path, or reload()), the previous data stays so the page does not jump or flash.
export function useApi(path, { refreshMs = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!path) return undefined
    const controller = new AbortController()
    setState((current) => ({ ...current, loading: true }))
    getJson(path, { signal: controller.signal })
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => {
        if (!controller.signal.aborted) setState((current) => ({ data: current.data, error, loading: false }))
      })
    return () => controller.abort()
  }, [path, attempt])

  useEffect(() => {
    if (!refreshMs) return undefined
    const id = setInterval(() => setAttempt((n) => n + 1), refreshMs)
    return () => clearInterval(id)
  }, [refreshMs])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  return { ...state, reload }
}

// Several loads treated as one. It has data only when ALL of them do, and shows the first error.
export function combineStates(states, merge) {
  return {
    data: states.every((s) => s.data) ? merge(states.map((s) => s.data)) : null,
    error: states.find((s) => s.error)?.error ?? null,
    loading: states.some((s) => s.loading),
    reload: () => states.forEach((s) => s.reload()),
  }
}

// Asks /health every few seconds and says which of three different things is wrong:
//   'ok'       the API answered and the database is reachable
//   'db-down'  the API answered, but with 503: it cannot reach PostgreSQL
//   'api-down' no answer at all
// (plus 'checking' for the first request and 'error' for anything unexpected)
export function useHealth(intervalMs = 15000) {
  const [health, setHealth] = useState({ status: 'checking', detail: null })

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    async function check() {
      try {
        const body = await getJson('/health', { signal: controller.signal, timeoutMs: 8000 })
        if (!cancelled) setHealth({ status: body.status === 'ok' ? 'ok' : 'error', detail: body })
      } catch (error) {
        if (cancelled || controller.signal.aborted) return
        if (error instanceof ApiError && error.kind === 'network') setHealth({ status: 'api-down', detail: error })
        else if (error instanceof ApiError && error.status === 503) setHealth({ status: 'db-down', detail: error })
        else setHealth({ status: 'error', detail: error })
      }
    }

    check()
    const id = setInterval(check, intervalMs)
    return () => {
      cancelled = true
      controller.abort()
      clearInterval(id)
    }
  }, [intervalMs])

  return health
}

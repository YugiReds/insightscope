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

// Keeps the header's status light up to date, and says which of three different things is wrong:
//   'ok'       the API answers AND its database answers
//   'db-down'  the API answers, but /health/db says the database cannot be reached (503)
//   'api-down' no answer from the API at all
// (plus 'checking' for the first request and 'error' for anything unexpected)
//
// It asks TWO questions, because they are two different routes:
//   /health     "is the API up?"  Cheap and never touches the database, so it is asked often (every 15 seconds).
//   /health/db  "is the database up?"  It wakes a sleeping database (Neon suspends it when idle), so it is asked
//               rarely: once at the start, again every minute, never while the tab is hidden, and straight away
//               after the API comes back from an outage. A forgotten browser tab must not keep the database awake.
export function useHealth(intervalMs = 15000, databaseIntervalMs = 60000) {
  const [health, setHealth] = useState({ status: 'checking', detail: null })

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    let database = null // what we last learned about the database: null (not known yet), 'ok' or 'down'
    let databaseError = null
    let lastDatabaseCheck = 0

    function failed(error) {
      if (error instanceof ApiError && error.kind === 'network') return { status: 'api-down', detail: error }
      return { status: 'error', detail: error }
    }

    async function check() {
      // 1. Is the API itself answering?
      try {
        await getJson('/health', { signal: controller.signal, timeoutMs: 8000 })
      } catch (error) {
        if (cancelled || controller.signal.aborted) return
        database = null // after an outage, look at the database again as soon as the API is back
        setHealth(failed(error))
        return
      }

      // 2. Is its database reachable? Only ask now and then (see the comment above).
      const now = Date.now()
      const due = database === null || (!document.hidden && now - lastDatabaseCheck >= databaseIntervalMs)
      if (due) {
        lastDatabaseCheck = now
        try {
          await getJson('/health/db', { signal: controller.signal, timeoutMs: 15000 })
          database = 'ok'
        } catch (error) {
          if (cancelled || controller.signal.aborted) return
          if (error instanceof ApiError && error.status === 503) {
            database = 'down'
            databaseError = error
          } else {
            database = null
            setHealth(failed(error))
            return
          }
        }
      }
      if (!cancelled) setHealth(database === 'down' ? { status: 'db-down', detail: databaseError } : { status: 'ok', detail: null })
    }

    check()
    const id = setInterval(check, intervalMs)
    return () => {
      cancelled = true
      controller.abort()
      clearInterval(id)
    }
  }, [intervalMs, databaseIntervalMs])

  return health
}

// Talks to the InsightScope API. Every failure becomes an ApiError that says WHICH kind of failure it was,
// because "the API is down", "the database is down" and "you asked for something invalid" need different messages.
//   kind 'network' : no answer at all (server stopped, no connection, or too slow)
//   kind 'http'    : the API answered with an error status (422 invalid request, 503 database down, ...)

export class ApiError extends Error {
  constructor(kind, message, { status = null, detail = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.detail = detail
  }
}

// FastAPI sends `detail` as text for our own errors, and as a list of {msg, loc, ...} for validation errors (422).
export function describeDetail(detail) {
  if (detail === null || detail === undefined) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => (item && item.msg) || JSON.stringify(item)).join('; ')
  return JSON.stringify(detail)
}

// The part both getJson and getFile share: send the request, give up after a time limit, and turn "could not
// connect" into a network ApiError. `readBody` then reads the answer in the way the caller needs.
async function request(path, { signal, timeoutMs, accept }, readBody) {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const forwardAbort = () => controller.abort()
  signal?.addEventListener('abort', forwardAbort)
  try {
    let response
    try {
      response = await fetch(path, { signal: controller.signal, headers: { Accept: accept } })
    } catch (error) {
      if (signal?.aborted) throw error // the caller cancelled (for example the section went away): not a failure to report
      throw new ApiError('network', timedOut ? `The API did not answer within ${timeoutMs / 1000} seconds.` : 'Could not connect to the API.')
    }
    return await readBody(response)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', forwardAbort)
  }
}

// An error answer from the API (a 422, a 503...) as an ApiError. The body is JSON with a `detail` when it is one of ours.
async function httpError(response) {
  let body = null
  try {
    body = await response.json()
  } catch {
    // the body was empty or not JSON
  }
  return new ApiError('http', `HTTP ${response.status}`, {
    status: response.status,
    detail: body && body.detail !== undefined ? body.detail : null,
  })
}

export function getJson(path, { signal, timeoutMs = 25000 } = {}) {
  return request(path, { signal, timeoutMs, accept: 'application/json' }, async (response) => {
    if (!response.ok) throw await httpError(response)
    let body = null
    try {
      body = await response.json()
    } catch {
      // not JSON
    }
    if (body === null) throw new ApiError('http', 'The API answered with something that is not JSON.', { status: response.status })
    return body
  })
}

// The file name the server chose, from a header like: attachment; filename="insightscope-recalls_all-dates.csv"
export function filenameFromDisposition(header) {
  const match = /filename="([^"]+)"/.exec(header ?? '')
  return match ? match[1] : null
}

// Downloads a file (the CSV reports). It waits longer than getJson, because the spike file may need the AI to
// write a summary the first time.
export function getFile(path, { signal, timeoutMs = 60000 } = {}) {
  return request(path, { signal, timeoutMs, accept: 'text/csv' }, async (response) => {
    if (!response.ok) throw await httpError(response)
    return { blob: await response.blob(), filename: filenameFromDisposition(response.headers.get('Content-Disposition')) }
  })
}

// Turns an error into plain words: a title, what happened, and what to check next.
export function explainError(error) {
  if (error instanceof ApiError) {
    if (error.kind === 'network') {
      return {
        title: "Can't reach the API",
        message: `${error.message} The server may be stopped, or the network is down.`,
        hint: 'Check that the API server is running (uvicorn main:app), then try again.',
      }
    }
    if (error.status === 503) {
      return {
        title: "The API can't reach its database",
        message: 'The API is running, but PostgreSQL is not answering (HTTP 503).',
        hint: 'Check that the database service is running and that DATABASE_URL is correct.',
      }
    }
    return {
      title: `The API returned an error (HTTP ${error.status})`,
      message: describeDetail(error.detail) || 'No further detail was given.',
      hint: error.status >= 500 ? 'This looks like a server problem. The API log has the details.' : null,
    }
  }
  return { title: 'Something went wrong in the dashboard', message: String((error && error.message) || error), hint: null }
}

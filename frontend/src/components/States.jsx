import { explainError } from '../api.js'
import { CrossIcon } from './icons.jsx'

// Shown while a section is loading for the first time.
export function LoadingBox({ label }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 rounded-lg border border-line bg-card p-4 text-ink-2">
      <span className="skeleton inline-block h-3 w-3 rounded-full" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

// Shown when something failed. It says in plain words WHAT failed, and what to check next.
export function ErrorBox({ error, onRetry, stale = false }) {
  const info = explainError(error)
  return (
    <div role="alert" className="rounded-lg border border-err-line bg-err-bg p-4 text-err-ink">
      <p className="flex items-center gap-2 font-semibold">
        <CrossIcon /> {stale ? `Could not refresh: ${info.title}` : info.title}
      </p>
      <p className="mt-1">{info.message}</p>
      {info.hint && <p className="mt-1 text-sm">{info.hint}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-3 rounded-md border border-err-line px-3 py-1.5 text-sm font-medium hover:bg-err-line/10">
          Try again
        </button>
      )}
    </div>
  )
}

// A titled card that shows the right thing for each state of one API call:
//   first load        -> a loading message
//   failed, no data   -> a clear error with a Try again button
//   has data          -> the content (dimmed while it refreshes, so the page never jumps)
//   failed to refresh -> the old content plus a note that the refresh failed
export function Section({ id, title, description, state, loadingLabel, children, headerExtras = null }) {
  const headingId = `${id}-heading`
  let body = null
  if (!state.data && state.loading) {
    body = <LoadingBox label={loadingLabel ?? `Loading ${title.toLowerCase()}…`} />
  } else if (!state.data && state.error) {
    body = <ErrorBox error={state.error} onRetry={state.reload} />
  } else if (state.data) {
    body = (
      <>
        {state.error && (
          <div className="mb-3">
            <ErrorBox error={state.error} onRetry={state.reload} stale />
            <p className="mt-1 text-sm text-ink-2">Showing the last data that loaded.</p>
          </div>
        )}
        <div aria-busy={state.loading} className={state.loading ? 'opacity-60 transition-opacity' : ''}>
          {children(state.data)}
        </div>
      </>
    )
  }
  return (
    <section aria-labelledby={headingId} className="rounded-xl border border-line bg-card p-5 shadow-sm">
      <h2 id={headingId} className="text-lg font-semibold">
        {title}
      </h2>
      {description && <p className="mt-1 text-sm text-ink-2">{description}</p>}
      {headerExtras}
      <div className="mt-4">{body}</div>
    </section>
  )
}

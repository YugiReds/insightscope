import { useRef, useState } from 'react'
import { ApiError, describeDetail, getJson } from '../api.js'
import { formatDate, formatInt } from '../format.js'
import { ErrorBox, LoadingBox } from './States.jsx'
import { CheckIcon, InfoIcon, WarnIcon } from './icons.jsx'

const PAGE_SIZE = 25
const EXAMPLES = [
  { ndc: '16729-455', note: 'has recalls' },
  { ndc: '99999-999', note: 'no recalls' },
  { ndc: 'abc', note: 'not an NDC' },
]

// Four different outcomes, each with its own icon, colour AND words, so they can never be mistaken for one another:
//   found    -> recalls listed                         (check icon, neutral card)
//   none     -> a valid NDC with no recalls on file    (info icon, blue)  NOT the same as "never recalled"
//   invalid  -> the API rejected the NDC (HTTP 422)    (warning icon, amber)
//   error    -> the API or database could not answer   (red, with a Try again button)
function Found({ ndc, data, onMore, loadingMore }) {
  return (
    <div role="region" aria-label={`Recalls for ${ndc}`} className="rounded-lg border border-line bg-card p-4">
      <p className="flex items-center gap-2 font-semibold">
        <CheckIcon style={{ color: 'var(--good)' }} />
        {formatInt(data.total)} {data.total === 1 ? 'recall lists' : 'recalls list'} NDC {ndc}
      </p>
      <p className="mt-1 text-sm text-ink-2">Newest first. Showing {formatInt(data.items.length)} of {formatInt(data.total)}.</p>
      <div className="mt-3 overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-160 text-left text-sm">
          <caption className="sr-only">Recalls that list NDC {ndc}</caption>
          <thead>
            <tr>
              <th scope="col" className="p-2">Recall number</th>
              <th scope="col" className="p-2">Reported</th>
              <th scope="col" className="p-2">Class</th>
              <th scope="col" className="p-2">Status</th>
              <th scope="col" className="p-2">Firm</th>
              <th scope="col" className="p-2">Reason</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.recall_number} className="border-t border-line align-top">
                <th scope="row" className="p-2 font-medium">{r.recall_number}</th>
                <td className="p-2 whitespace-nowrap">{r.report_date ? formatDate(r.report_date) : 'Not given'}</td>
                <td className="p-2 whitespace-nowrap">{r.classification ?? 'Not given'}</td>
                <td className="p-2">{r.status ?? 'Not given'}</td>
                <td className="p-2">{r.recalling_firm ?? 'Not given'}</td>
                <td className="p-2 max-w-md">{r.reason_for_recall ?? 'Not given'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.items.length < data.total && (
        <button
          type="button"
          onClick={onMore}
          disabled={loadingMore}
          className="mt-3 rounded-md border border-line bg-card px-3 py-1.5 text-sm font-medium hover:bg-line/40 disabled:opacity-60"
        >
          {loadingMore ? 'Loading…' : `Show ${Math.min(PAGE_SIZE, data.total - data.items.length)} more`}
        </button>
      )}
    </div>
  )
}

function NoRecalls({ ndc }) {
  return (
    <div role="status" className="rounded-lg border border-info-line bg-info-bg p-4">
      <p className="flex items-center gap-2 font-semibold">
        <InfoIcon /> No recalls found for {ndc}
      </p>
      <p className="mt-1">This NDC is in the right format, but no recall in our data lists it.</p>
      <p className="mt-1 text-sm">
        That does not prove it was never recalled. We hold only the newest recalls, and only about one recall in four names any NDC. For a safety decision, check the FDA directly.
      </p>
    </div>
  )
}

function InvalidNdc({ ndc, error }) {
  const detail = describeDetail(error.detail)
  return (
    <div role="alert" className="rounded-lg border border-warn-line bg-warn-bg p-4 text-warn-ink">
      <p className="flex items-center gap-2 font-semibold">
        <WarnIcon /> That does not look like a valid NDC
      </p>
      <p className="mt-1">The API rejected “{ndc}” (HTTP 422), so no search was done.</p>
      {detail && <p className="mt-1 text-sm">The API said: {detail}</p>}
      <p className="mt-1 text-sm">An NDC is 4 or 5 digits, a hyphen, then 1 to 4 digits, for example 16729-455.</p>
    </div>
  )
}

export default function NdcLookup() {
  const [ndc, setNdc] = useState('')
  const [result, setResult] = useState({ phase: 'idle' })
  const [loadingMore, setLoadingMore] = useState(false)
  const controller = useRef(null)

  async function search(value) {
    const wanted = value.trim()
    if (!wanted) {
      setResult({ phase: 'empty' })
      return
    }
    controller.current?.abort()
    controller.current = new AbortController()
    const { signal } = controller.current
    setResult({ phase: 'loading', ndc: wanted })
    try {
      const data = await getJson(`/products/${encodeURIComponent(wanted)}/recalls?limit=${PAGE_SIZE}`, { signal })
      setResult({ phase: data.total > 0 ? 'found' : 'none', ndc: wanted, data })
    } catch (error) {
      if (signal.aborted) return
      const invalid = error instanceof ApiError && error.status === 422
      setResult({ phase: invalid ? 'invalid' : 'error', ndc: wanted, error })
    }
  }

  async function showMore() {
    setLoadingMore(true)
    try {
      const more = await getJson(`/products/${encodeURIComponent(result.ndc)}/recalls?limit=${PAGE_SIZE}&offset=${result.data.items.length}`)
      setResult((current) => ({ ...current, data: { ...more, items: [...current.data.items, ...more.items] } }))
    } catch (error) {
      setResult({ phase: 'error', ndc: result.ndc, error })
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <section aria-labelledby="ndc-heading" className="rounded-xl border border-line bg-card p-5 shadow-sm">
      <h2 id="ndc-heading" className="text-lg font-semibold">Has this drug been recalled?</h2>
      <p className="mt-1 text-sm text-ink-2">Look up a drug by its NDC, the drug's national code.</p>

      <form
        className="mt-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          search(ndc)
        }}
      >
        <div className="flex flex-col">
          <label htmlFor="ndc-input" className="text-sm font-medium">NDC</label>
          <input
            id="ndc-input"
            type="text"
            inputMode="text"
            autoComplete="off"
            value={ndc}
            onChange={(e) => setNdc(e.target.value)}
            aria-describedby="ndc-hint"
            className="w-56 rounded-md border border-line bg-card px-3 py-2"
          />
        </div>
        <button type="submit" className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-on-accent">
          Check recalls
        </button>
      </form>
      <p id="ndc-hint" className="mt-2 text-sm text-ink-2">Format: 4 or 5 digits, a hyphen, then 1 to 4 digits, like 16729-455.</p>
      <p className="mt-2 text-sm text-ink-2">
        Try an example:{' '}
        {EXAMPLES.map((ex) => (
          <button
            key={ex.ndc}
            type="button"
            onClick={() => {
              setNdc(ex.ndc)
              search(ex.ndc)
            }}
            className="mr-3 text-accent-ink underline"
          >
            {ex.ndc} ({ex.note})
          </button>
        ))}
      </p>

      <div className="mt-4" aria-live="polite">
        {result.phase === 'empty' && (
          <div role="alert" className="rounded-lg border border-warn-line bg-warn-bg p-4 text-warn-ink">
            <p className="flex items-center gap-2 font-semibold"><WarnIcon /> Type an NDC first</p>
          </div>
        )}
        {result.phase === 'loading' && <LoadingBox label={`Checking recalls for ${result.ndc}…`} />}
        {result.phase === 'found' && <Found ndc={result.ndc} data={result.data} onMore={showMore} loadingMore={loadingMore} />}
        {result.phase === 'none' && <NoRecalls ndc={result.ndc} />}
        {result.phase === 'invalid' && <InvalidNdc ndc={result.ndc} error={result.error} />}
        {result.phase === 'error' && <ErrorBox error={result.error} onRetry={() => search(result.ndc)} />}
      </div>
    </section>
  )
}

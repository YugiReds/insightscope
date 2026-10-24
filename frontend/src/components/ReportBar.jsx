import { useState } from 'react'
import { getFile } from '../api.js'
import { saveFile } from '../download.js'
import { describeRange } from '../format.js'
import { CheckIcon } from './icons.jsx'
import { ErrorBox, LoadingBox } from './States.jsx'

const BUTTON = 'inline-flex items-center rounded-md border border-line bg-card px-4 py-2 text-sm font-semibold hover:bg-line/40'
const PRIMARY = 'inline-flex items-center rounded-md bg-accent px-4 py-2 text-sm font-semibold text-on-accent'

export const SPIKES_HREF = '/reports/spikes.csv'

// The address of the recalls file for the chosen date range. With no range it is just /reports/recalls.csv.
export function recallsHref({ from, to }) {
  const params = new URLSearchParams()
  if (from) params.set('start', from)
  if (to) params.set('end', to)
  const query = params.toString()
  return `/reports/recalls.csv${query ? `?${query}` : ''}`
}

// The "Download report" area: two CSV files and a Print / Save as PDF button.
// The download buttons are real links (right-click "copy link" works), but a click is handled here instead: the page
// fetches the file itself, so that if the API is down or rejects the request, the user reads a clear message instead
// of getting a broken download.
export default function ReportBar({ range }) {
  const [status, setStatus] = useState({ phase: 'idle' })
  const recalls = recallsHref(range)

  async function run(href, label) {
    setStatus({ phase: 'loading', href, label })
    try {
      const { blob, filename } = await getFile(href)
      const name = filename ?? href.split('?')[0].split('/').pop()
      saveFile(blob, name)
      setStatus({ phase: 'done', filename: name })
    } catch (error) {
      setStatus({ phase: 'error', href, label, error })
    }
  }

  function download(event, href, label) {
    event.preventDefault()
    run(href, label)
  }

  return (
    <section aria-labelledby="report-heading" className="rounded-xl border border-line bg-card p-5 shadow-sm print:hidden">
      <h2 id="report-heading" className="text-lg font-semibold">Download report</h2>
      <p className="mt-1 text-sm text-ink-2">Take the data with you: two spreadsheet files (CSV) and a printable page.</p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {range.error ? (
          <button type="button" disabled aria-describedby="report-range-error" className={`${BUTTON} opacity-60`}>
            Download recalls (CSV)
          </button>
        ) : (
          <a href={recalls} download onClick={(event) => download(event, recalls, 'recalls')} className={BUTTON}>
            Download recalls (CSV)
          </a>
        )}
        <a href={SPIKES_HREF} download onClick={(event) => download(event, SPIKES_HREF, 'spike summaries')} className={BUTTON}>
          Download spike summaries (CSV)
        </a>
        <button type="button" onClick={() => window.print()} className={PRIMARY}>
          Print / Save as PDF
        </button>
      </div>

      <p className="mt-3 text-sm text-ink-2">
        The recalls file has one row per recall ({describeRange(range.from, range.to)}), newest first, and follows the date range chosen
        under “Why drugs are recalled”. The spike file has one row per spike month with its summary, and always covers every spike.
      </p>
      {range.error && (
        <p id="report-range-error" role="alert" className="mt-2 text-sm font-medium text-err-ink">
          Fix the date range under “Why drugs are recalled” first. {range.error}
        </p>
      )}

      <div className="mt-3" aria-live="polite">
        {status.phase === 'loading' && (
          <LoadingBox
            label={`Preparing the ${status.label} file…${status.label === 'spike summaries' ? ' The first time can take a few seconds, because an AI writes the summaries.' : ''}`}
          />
        )}
        {status.phase === 'done' && (
          <p role="status" className="flex items-center gap-2 text-sm font-medium">
            <CheckIcon style={{ color: 'var(--good)' }} /> Downloaded {status.filename}
          </p>
        )}
        {status.phase === 'error' && <ErrorBox error={status.error} onRetry={() => run(status.href, status.label)} />}
      </div>

      <p className="mt-2 text-xs text-ink-2">
        Print / Save as PDF opens your browser's print window. Pick “Save as PDF” as the printer to get a file. The printed page
        always uses light colours, even if your screen is in dark mode.
      </p>
    </section>
  )
}

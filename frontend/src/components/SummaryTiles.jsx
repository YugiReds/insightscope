import { explainError } from '../api.js'
import { combineStates } from '../hooks.js'
import { formatDate, formatInt, formatMonth, formatPercent } from '../format.js'

// One headline number. Each tile has its own loading and error state, so one failed call never blanks the others.
function Tile({ label, state, children }) {
  return (
    <div className="rounded-xl border border-line bg-card p-4 shadow-sm">
      <p className="text-sm text-ink-2">{label}</p>
      {state.data ? (
        <div aria-busy={state.loading}>{children(state.data)}</div>
      ) : state.error ? (
        <div role="alert" className="mt-1">
          <p className="font-medium">Unavailable</p>
          <p className="text-sm text-ink-2">{explainError(state.error).title}</p>
          <button type="button" onClick={state.reload} className="mt-1 text-sm font-medium text-accent-ink underline print:hidden">
            Try again
          </button>
        </div>
      ) : (
        <div role="status" aria-label={`Loading ${label}`} className="skeleton mt-2 h-8 w-28 rounded" />
      )}
    </div>
  )
}

const Value = ({ children, small = false }) => <p className={`mt-1 font-semibold ${small ? 'text-xl' : 'text-3xl'}`}>{children}</p>
const Sub = ({ children }) => <p className="mt-1 text-sm text-ink-2">{children}</p>

export default function SummaryTiles({ total, classOne, spikes, monthly }) {
  const classShare = combineStates([total, classOne], ([all, one]) => ({ all: all.total, one: one.total }))
  return (
    <section aria-label="Summary" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 print:grid-cols-4">
      <Tile label="Total recalls" state={total}>
        {(data) => (
          <>
            <Value>{formatInt(data.total)}</Value>
            <Sub>in the loaded data (the newest recalls)</Sub>
          </>
        )}
      </Tile>

      <Tile label="Class I share" state={classShare}>
        {({ all, one }) => (
          <>
            <Value>{all ? formatPercent(one / all) : '0%'}</Value>
            <Sub>
              {formatInt(one)} of {formatInt(all)} recalls are Class I, the most serious class
            </Sub>
          </>
        )}
      </Tile>

      <Tile label="Spike months" state={spikes}>
        {(data) => (
          <>
            <Value>{formatInt(data.spikes.length)}</Value>
            <Sub>
              of {formatInt(data.months_scored)} months scored (z-score above {data.threshold})
            </Sub>
          </>
        )}
      </Tile>

      <Tile label="Date range covered" state={monthly}>
        {(data) => {
          const c = data.coverage
          if (!c) return <Value small>No recalls loaded</Value>
          return (
            <>
              <Value small>
                {formatDate(c.oldest_report_date)} – {formatDate(c.newest_report_date)}
              </Value>
              <Sub>
                {c.excluded_oldest_month
                  ? `Charts start ${formatMonth(c.first_full_month)}, because ${formatMonth(c.excluded_oldest_month)} is only partly covered.`
                  : 'Every month in the range is fully covered.'}
                {c.newest_month_may_be_incomplete ? ' The latest month may be unfinished.' : ''}
              </Sub>
            </>
          )
        }}
      </Tile>
    </section>
  )
}

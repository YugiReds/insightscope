import { Bar, BarChart, LabelList, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi, useDateRange } from '../hooks.js'
import { describeRange, formatDate, formatInt, formatPercent, monthsBefore } from '../format.js'
import ChartFrame from './ChartFrame.jsx'
import { Section } from './States.jsx'

// A bar that grows from the baseline with a rounded tip. "Other" (nothing matched a keyword rule) is grey so it
// reads as the leftover bucket, and the real categories share one colour because they are not ranked by colour.
function Bar4({ x, y, width, height, payload }) {
  if (!width || width <= 0) return null
  const r = Math.min(4, width, height / 2)
  const fill = payload.category === 'Other' ? 'var(--class-other)' : 'var(--series-1)'
  return <path d={`M${x} ${y}h${width - r}a${r} ${r} 0 0 1 ${r} ${r}v${height - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(width - r)}Z`} fill={fill} />
}

function ReasonTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const row = payload[0].payload
  return (
    <div className="rounded-lg border border-line bg-card p-3 text-sm shadow-lg">
      <p className="font-semibold">{row.category}</p>
      <p className="mt-1">
        <span className="text-lg font-semibold">{formatInt(row.recalls)}</span> <span className="text-ink-2">recalls ({formatPercent(row.share)})</span>
      </p>
    </div>
  )
}

export function summarizeReasons(data) {
  if (!data.total) return 'There are no recalls in this date range.'
  const top = data.categories[0]
  return (
    `Of ${formatInt(data.total)} recalls, ${top.category} is the largest reason (${formatPercent(top.share)}). ` +
    `"Other", the recalls that match none of the keyword rules, is ${formatPercent(data.other_share)}.`
  )
}

function ReasonsBody({ data }) {
  const rows = data.categories.map((c) => ({ ...c, label: `${formatInt(c.recalls)} · ${formatPercent(c.share)}` }))
  return (
    <figure>
      <ChartFrame height={rows.length * 38 + 16} printHeight={rows.length * 30 + 16} initialWidth={700}>
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 8, bottom: 4, left: 0 }} barCategoryGap="22%">
            <XAxis type="number" hide domain={[0, (max) => Math.max(1, max * 1.4)]} />
            <YAxis
              type="category"
              dataKey="category"
              width={180}
              tick={{ fill: 'var(--ink-2)', fontSize: 13 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--axis)' }}
            />
            <Tooltip content={<ReasonTooltip />} cursor={{ fill: 'var(--line)', fillOpacity: 0.5 }} />
            <Bar dataKey="recalls" barSize={20} shape={<Bar4 />} isAnimationActive={false}>
              <LabelList dataKey="label" position="right" style={{ fill: 'var(--ink-2)', fontSize: 12 }} />
            </Bar>
          </BarChart>
      </ChartFrame>
      <figcaption className="mt-2 text-sm text-ink-2" data-testid="reasons-summary">
        {summarizeReasons(data)}
      </figcaption>

      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-accent-ink underline">View this chart as a table</summary>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">Recalls by reason category</caption>
          <thead>
            <tr>
              <th scope="col" className="p-2">Reason category</th>
              <th scope="col" className="p-2 text-right">Recalls</th>
              <th scope="col" className="p-2 text-right">Share</th>
            </tr>
          </thead>
          <tbody>
            {data.categories.map((c) => (
              <tr key={c.category} className="border-t border-line">
                <th scope="row" className="p-2 font-normal">{c.category}</th>
                <td className="p-2 text-right">{formatInt(c.recalls)}</td>
                <td className="p-2 text-right">{formatPercent(c.share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      {data.top_other_reasons.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-accent-ink underline">What is in "Other"?</summary>
          <p className="mt-2 text-sm text-ink-2">The most common reasons that matched none of the keyword rules. If this list grows, the rules need updating.</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {data.top_other_reasons.map((r) => (
              <li key={r.reason}>
                {r.reason} ({formatInt(r.recalls)})
              </li>
            ))}
          </ul>
        </details>
      )}
    </figure>
  )
}

// The date range picker sits above the chart it filters. "Presets" (all time, last 12 or 24 months) are one click;
// the two date boxes are for a custom range. A backwards range is caught here, before anything is sent.
export default function ReasonCategories({ coverage, range }) {
  // The page normally shares one date range with the download buttons and the printout. If none is passed in
  // (for example in a test), this section keeps its own.
  const own = useDateRange()
  const { from, to, setFrom, setTo, error: rangeError } = range ?? own

  const params = new URLSearchParams()
  if (from) params.set('start', from)
  if (to) params.set('end', to)
  const query = params.toString()
  const state = useApi(rangeError ? null : `/analytics/recalls/reasons${query ? `?${query}` : ''}`)

  const newest = coverage?.newest_report_date
  const presets = [
    { label: 'All time', from: '', to: '' },
    ...(newest
      ? [
          { label: 'Last 12 months', from: monthsBefore(newest, 12), to: newest },
          { label: 'Last 24 months', from: monthsBefore(newest, 24), to: newest },
        ]
      : []),
  ]

  const picker = (
    <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-3">
      <div className="flex flex-col">
        <label htmlFor="reasons-from" className="text-sm font-medium">From</label>
        <input
          id="reasons-from"
          type="date"
          value={from}
          min={coverage?.oldest_report_date}
          max={coverage?.newest_report_date}
          onChange={(e) => setFrom(e.target.value)}
          aria-describedby={rangeError ? 'reasons-range-error' : undefined}
          aria-invalid={rangeError ? 'true' : undefined}
          className="rounded-md border border-line bg-card px-2 py-1.5"
        />
      </div>
      <div className="flex flex-col">
        <label htmlFor="reasons-to" className="text-sm font-medium">To</label>
        <input
          id="reasons-to"
          type="date"
          value={to}
          min={coverage?.oldest_report_date}
          max={coverage?.newest_report_date}
          onChange={(e) => setTo(e.target.value)}
          aria-describedby={rangeError ? 'reasons-range-error' : undefined}
          aria-invalid={rangeError ? 'true' : undefined}
          className="rounded-md border border-line bg-card px-2 py-1.5"
        />
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Date range presets">
        {presets.map((p) => {
          const active = p.from === from && p.to === to
          return (
            <button
              key={p.label}
              type="button"
              aria-pressed={active}
              onClick={() => {
                setFrom(p.from)
                setTo(p.to)
              }}
              className={`rounded-md border px-3 py-1.5 text-sm font-medium ${active ? 'border-accent bg-accent text-on-accent' : 'border-line bg-card hover:bg-line/40'}`}
            >
              {p.label}
            </button>
          )
        })}
      </div>
      {rangeError && (
        <p id="reasons-range-error" role="alert" className="basis-full text-sm font-medium text-err-ink">
          {rangeError}
        </p>
      )}
      {!rangeError && (from || to) && (
        <p className="basis-full text-sm text-ink-2">
          Showing recalls reported {from ? `from ${formatDate(from)}` : 'from the start'} {to ? `to ${formatDate(to)}` : 'to the latest report'}.
        </p>
      )}
    </div>
  )

  return (
    <Section
      id="reasons"
      title="Why drugs are recalled"
      description="Each recall's reason is sorted into a category by keyword rules."
      state={state}
      loadingLabel="Loading reason categories…"
      headerExtras={
        <>
          <div className="print:hidden">{picker}</div>
          <p className="mt-2 hidden text-sm print:block">Recalls included: {describeRange(from, to)}.</p>
        </>
      }
    >
      {(data) => <ReasonsBody data={data} />}
    </Section>
  )
}

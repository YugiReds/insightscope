import { CartesianGrid, ComposedChart, Bar, Line, Tooltip, XAxis, YAxis } from 'recharts'
import { explainError } from '../api.js'
import { compactNumber, formatInt, formatMonth, formatPercent } from '../format.js'
import ChartFrame from './ChartFrame.jsx'
import { DiamondIcon } from './icons.jsx'

// Recall classes are ordered by severity, so they share one blue ramp (darker = more serious).
// Any class we do not know about gets the neutral grey, so a new class never breaks the chart.
const CLASS_ORDER = ['Class I', 'Class II', 'Class III']
const CLASS_COLOR = { 'Class I': 'var(--class-1)', 'Class II': 'var(--class-2)', 'Class III': 'var(--class-3)' }
const colorOf = (name) => CLASS_COLOR[name] ?? 'var(--class-other)'
const orderClasses = (names) => [...names].sort((a, b) => {
  const ia = CLASS_ORDER.indexOf(a)
  const ib = CLASS_ORDER.indexOf(b)
  return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b)
})

// The sentence that stands in for the chart for anyone who cannot see it. The table below has every number.
export function summarizeMonthly(data, spikeMonths = []) {
  const months = data.months
  if (!months.length) return 'There is no monthly data to chart yet.'
  const busiest = months.reduce((best, m) => (m.total > best.total ? m : best))
  const byClass = {}
  let grand = 0
  months.forEach((m) => {
    grand += m.total
    Object.entries(m.by_classification).forEach(([name, n]) => {
      byClass[name] = (byClass[name] ?? 0) + n
    })
  })
  const shares = orderClasses(Object.keys(byClass))
    .filter((name) => byClass[name] > 0)
    .map((name) => {
      const share = byClass[name] / grand
      return `${name} ${share < 0.005 ? 'under 1%' : formatPercent(share, 0)}`
    })
  let text =
    `Recalls per month from ${formatMonth(months[0].month)} to ${formatMonth(months[months.length - 1].month)} ` +
    `(${months.length} months). The busiest month was ${formatMonth(busiest.month)} with ${formatInt(busiest.total)} recalls. ` +
    `By class: ${shares.join(', ')}.`
  text += spikeMonths.length
    ? ` ${spikeMonths.length} months are marked as spikes: ${spikeMonths.map((m) => formatMonth(m)).join(', ')}.`
    : ' No spike months are marked.'
  return text
}

// One stacked segment. Insetting each by 1px at the top and bottom leaves a 2px gap of card colour between segments.
function Segment({ x, y, width, height, fill }) {
  if (!height || height <= 0) return null
  const gap = height > 3 ? 1 : 0
  return <rect x={x} y={y + gap} width={width} height={height - gap * 2} fill={fill} />
}

// The spike marker: a diamond just above the month's bar, with a ring in the card colour so it stays clear of the bars.
function SpikeDot({ cx, cy, value }) {
  if (value === null || value === undefined || cx === undefined) return null
  const y = cy - 11
  return <path d={`M${cx} ${y - 7}L${cx + 6} ${y}L${cx} ${y + 7}L${cx - 6} ${y}Z`} fill="var(--ink)" stroke="var(--card)" strokeWidth="2" />
}

// Hovering OR keyboard-focusing a month shows the same readout: value first, name second.
function ChartTooltip({ active, payload, label, spikeSet }) {
  if (!active || !payload || !payload.length) return null
  const row = payload[0].payload
  const entries = payload.filter((p) => p.dataKey !== 'spikeY' && p.value > 0).reverse()
  return (
    <div className="rounded-lg border border-line bg-card p-3 text-sm shadow-lg">
      <p className="font-semibold">{formatMonth(label, 'long')}</p>
      <p className="mt-1">
        <span className="text-lg font-semibold">{formatInt(row.total)}</span> <span className="text-ink-2">recalls</span>
      </p>
      <ul className="mt-1">
        {entries.map((p) => (
          <li key={p.dataKey} className="mt-1 flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-0.75 w-4" style={{ background: p.color }} />
            <span className="font-semibold">{formatInt(p.value)}</span>
            <span className="text-ink-2">{p.name}</span>
          </li>
        ))}
      </ul>
      {spikeSet.has(label) && (
        <p className="mt-2 flex items-center gap-1 font-medium">
          <DiamondIcon /> Spike month
        </p>
      )}
    </div>
  )
}

export default function MonthlyChart({ monthly, spikes }) {
  const spikeMonths = spikes.data ? spikes.data.spikes.map((s) => s.month) : []
  const spikeSet = new Set(spikeMonths)
  const classes = orderClasses(monthly.classifications)
  const rows = monthly.months.map((m) => ({
    month: m.month,
    total: m.total,
    ...m.by_classification,
    spikeY: spikeSet.has(m.month) ? m.total : null,
  }))
  const yearTicks = rows.filter((r) => r.month.endsWith('-01')).map((r) => r.month)
  const summary = summarizeMonthly(monthly, spikeMonths)

  if (!rows.length) return <p>{summary}</p>

  return (
    <figure>
      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm" aria-label="Chart legend">
        {classes.map((name) => (
          <li key={name} className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-3 w-3 rounded-sm" style={{ background: colorOf(name) }} />
            {name}
            {name === 'Class I' && <span className="text-ink-2">(most serious)</span>}
          </li>
        ))}
        <li className="flex items-center gap-2">
          <DiamondIcon /> Spike month
        </li>
      </ul>

      <ChartFrame className="mt-3" height={340} printHeight={250} initialWidth={900}>
          <ComposedChart data={rows} margin={{ top: 22, right: 12, bottom: 4, left: 0 }} barCategoryGap="12%">
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis
              dataKey="month"
              ticks={yearTicks}
              interval={0}
              tickFormatter={(m) => m.slice(0, 4)}
              tick={{ fill: 'var(--ink-2)', fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--axis)' }}
            />
            <YAxis
              tickFormatter={compactNumber}
              tick={{ fill: 'var(--ink-2)', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={44}
              domain={[0, 'auto']}
            />
            <Tooltip content={<ChartTooltip spikeSet={spikeSet} />} cursor={{ fill: 'var(--line)', fillOpacity: 0.5 }} />
            {classes.map((name) => (
              <Bar key={name} dataKey={name} name={name} stackId="recalls" fill={colorOf(name)} maxBarSize={24} shape={<Segment />} isAnimationActive={false} />
            ))}
            <Line dataKey="spikeY" name="Spike month" stroke="none" dot={<SpikeDot />} activeDot={false} isAnimationActive={false} legendType="none" />
          </ComposedChart>
      </ChartFrame>

      <figcaption className="mt-3 text-sm text-ink-2" data-testid="chart-summary">
        {summary}
      </figcaption>
      {spikes.error && (
        <p role="alert" className="mt-2 text-sm text-err-ink">
          Spike markers could not be loaded ({explainError(spikes.error).title}), so none are shown on the chart.
        </p>
      )}

      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-accent-ink underline">View this chart as a table</summary>
        <div className="mt-2 max-h-80 overflow-auto rounded-lg border border-line">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Recalls per month by classification</caption>
            <thead className="sticky top-0 bg-card">
              <tr>
                <th scope="col" className="p-2">Month</th>
                <th scope="col" className="p-2">Spike</th>
                <th scope="col" className="p-2 text-right">Total</th>
                {classes.map((name) => (
                  <th key={name} scope="col" className="p-2 text-right">{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {monthly.months.map((m) => (
                <tr key={m.month} className="border-t border-line">
                  <th scope="row" className="p-2 font-normal">{formatMonth(m.month)}</th>
                  <td className="p-2">{spikeSet.has(m.month) ? 'Spike' : ''}</td>
                  <td className="p-2 text-right font-semibold">{formatInt(m.total)}</td>
                  {classes.map((name) => (
                    <td key={name} className="p-2 text-right">{formatInt(m.by_classification[name] ?? 0)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  )
}

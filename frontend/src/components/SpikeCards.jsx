import { formatInt, formatMonth } from '../format.js'
import { CheckIcon, InfoIcon } from './icons.jsx'

// The badge says where a summary came from. For a template it also gives the reason the AI was not used:
// on hover, on keyboard focus (it is focusable), and to screen readers (aria-label).
export function SourceBadge({ source, reason, model }) {
  const isAi = source === 'ai'
  const label = isAi ? 'AI' : 'Template'
  const explanation = isAi
    ? `Written by an AI model${model ? ` (${model})` : ''} from facts our code computed. Every number was checked against those facts.`
    : `Why the AI was not used: ${reason || 'no reason was given'}`
  return (
    <span
      tabIndex={0}
      title={explanation}
      aria-label={`${label} summary. ${explanation}`}
      data-source={source}
      className={`inline-flex shrink-0 cursor-help items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${isAi ? 'bg-ai-bg text-ai-ink' : 'bg-tpl-bg text-tpl-ink'}`}
    >
      {isAi ? <CheckIcon width={14} height={14} /> : <InfoIcon width={14} height={14} />}
      {label}
    </span>
  )
}

// What the share of the month that the top firm accounts for means, in words (decided by the API, not by the AI).
const DRIVER_TEXT = {
  one_firm: "Mainly one firm's mass recall",
  large_share: 'One firm drove a large part',
  spread: 'No single firm dominates',
  unknown: 'Firm not recorded',
}

function UsualBars({ count, usual }) {
  const usualWidth = count > 0 ? Math.min(100, (usual / count) * 100) : 0
  return (
    <div className="mt-3 space-y-1.5" aria-hidden="true">
      <div className="flex items-center gap-2 text-xs text-ink-2">
        <span className="w-16">This month</span>
        <span className="h-2 flex-1 rounded bg-line">
          <span className="block h-2 rounded" style={{ width: '100%', background: 'var(--class-1)' }} />
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-ink-2">
        <span className="w-16">Usual</span>
        <span className="h-2 flex-1 rounded bg-line">
          <span className="block h-2 rounded" style={{ width: `${usualWidth}%`, background: 'var(--class-3)' }} />
        </span>
      </div>
    </div>
  )
}

export function SpikeCard({ spike, model }) {
  const facts = spike.facts
  const firm = facts.top_recalling_firms[0]
  const usual = Math.round(facts.baseline_mean)
  const headingId = `spike-${spike.month}`
  return (
    <article aria-labelledby={headingId} className="flex flex-col rounded-xl border border-line bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h3 id={headingId} className="text-lg font-semibold">
          {formatMonth(spike.month, 'long')}
        </h3>
        <SourceBadge source={spike.source} reason={spike.fallback_reason} model={model} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <dt className="text-sm text-ink-2">Recalls</dt>
          <dd className="text-2xl font-semibold">{formatInt(facts.recalls)}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-2">Usual level</dt>
          <dd className="text-2xl font-semibold">
            {formatInt(usual)} <span className="text-sm font-normal text-ink-2">a month</span>
          </dd>
        </div>
      </dl>
      <UsualBars count={facts.recalls} usual={usual} />
      <p className="mt-2 text-sm text-ink-2">z-score {facts.z_score.toFixed(1)} against the previous 12 months</p>

      {firm && (
        <p className="mt-3 text-sm">
          <span className="text-ink-2">Top firm: </span>
          <strong>{firm.recalling_firm}</strong>, {formatInt(firm.recalls)} recalls, {facts.top_firm_share_pct}% of the month
        </p>
      )}
      <p className="mt-1 text-sm font-medium">{DRIVER_TEXT[facts.driver] ?? ''}</p>

      <p className="mt-3 leading-relaxed">{spike.summary}</p>
      {spike.source === 'ai' && spike.cached && <p className="mt-2 text-xs text-ink-2">Saved summary (reused from the cache)</p>}
    </article>
  )
}

export default function SpikeCards({ data }) {
  if (!data.spikes.length) return <p>No spike months were found in the loaded data.</p>
  return (
    <div>
      <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.spikes.map((spike) => (
          <li key={spike.month} className="flex">
            <div className="flex w-full">
              <SpikeCard spike={spike} model={data.model} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

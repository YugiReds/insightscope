import { CheckIcon, CrossIcon, InfoIcon, WarnIcon } from './icons.jsx'

// The live indicator in the header. It tells apart the three situations a support engineer needs to separate:
// everything fine, the API is up but its database is not, and the API cannot be reached at all.
const VIEWS = {
  checking: { Icon: InfoIcon, label: 'Checking the API…', color: 'var(--ink-2)' },
  ok: { Icon: CheckIcon, label: 'API and database OK', color: 'var(--good)' },
  'db-down': { Icon: WarnIcon, label: 'API is up, database unavailable', color: 'var(--warning)' },
  'api-down': { Icon: CrossIcon, label: 'API unreachable', color: 'var(--critical)' },
  error: { Icon: WarnIcon, label: 'API gave an unexpected answer', color: 'var(--warning)' },
}

export default function StatusIndicator({ health }) {
  const { Icon, label, color } = VIEWS[health.status] ?? VIEWS.error
  return (
    <div role="status" aria-live="polite" data-status={health.status} className="flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-sm font-medium">
      <span style={{ color }}>
        <Icon />
      </span>
      <span>{label}</span>
    </div>
  )
}

import { useEffect, useRef } from 'react'
import { useApi, useHealth } from './hooks.js'
import MonthlyChart from './components/MonthlyChart.jsx'
import NdcLookup from './components/NdcLookup.jsx'
import ReasonCategories from './components/ReasonCategories.jsx'
import SpikeCards from './components/SpikeCards.jsx'
import StatusIndicator from './components/StatusIndicator.jsx'
import { Section } from './components/States.jsx'
import SummaryTiles from './components/SummaryTiles.jsx'
import { CrossIcon, WarnIcon } from './components/icons.jsx'

// A banner that says plainly what is wrong when the API or its database is down, so the page is never just blank.
function OutageBanner({ status }) {
  if (status === 'api-down') {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-xl border border-err-line bg-err-bg p-4 text-err-ink">
        <CrossIcon className="mt-0.5 shrink-0" />
        <div>
          <p className="font-semibold">The InsightScope API is not answering.</p>
          <p className="text-sm">Nothing below can load until it is back. The server may be stopped or the network is down. The sections will reload by themselves when it recovers.</p>
        </div>
      </div>
    )
  }
  if (status === 'db-down') {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-xl border border-warn-line bg-warn-bg p-4 text-warn-ink">
        <WarnIcon className="mt-0.5 shrink-0" />
        <div>
          <p className="font-semibold">The API is running, but it cannot reach its database.</p>
          <p className="text-sm">The data sections will show errors until PostgreSQL is back. They will reload by themselves when it recovers.</p>
        </div>
      </div>
    )
  }
  return null
}

export default function App() {
  const health = useHealth()
  const total = useApi('/recalls?limit=1')
  const classOne = useApi('/recalls?classification=Class%20I&limit=1')
  const monthly = useApi('/analytics/recalls/monthly')
  const spikes = useApi('/analytics/recalls/spikes')
  const insights = useApi('/insights/recalls/spikes')

  // When the API comes back after an outage, reload every section that failed instead of making the user click.
  const wasDown = useRef(false)
  useEffect(() => {
    if (health.status === 'api-down' || health.status === 'db-down') wasDown.current = true
    if (health.status === 'ok' && wasDown.current) {
      wasDown.current = false
      ;[total, classOne, monthly, spikes, insights].forEach((state) => state.error && state.reload())
    }
  }, [health.status]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-card focus:px-3 focus:py-2">
        Skip to the dashboard
      </a>
      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div>
            <h1 className="text-xl font-semibold">InsightScope</h1>
            <p className="text-sm text-ink-2">FDA drug recall analytics</p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <a href="/docs" className="text-sm font-medium text-accent-ink underline">
              API docs
            </a>
            <StatusIndicator health={health} />
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <OutageBanner status={health.status} />

        <SummaryTiles total={total} classOne={classOne} spikes={spikes} monthly={monthly} />

        <Section
          id="monthly"
          title="Recalls per month"
          description="Recalls by the month they were reported, split by classification. Diamonds mark spike months."
          state={monthly}
          loadingLabel="Loading monthly recall counts…"
        >
          {(data) => <MonthlyChart monthly={data} spikes={spikes} />}
        </Section>

        <Section
          id="spikes"
          title="Spike months"
          description="Months with unusually many recalls compared with the previous 12 months, each with a plain-English summary."
          state={insights}
          loadingLabel="Writing the spike summaries. The first visit can take a few seconds because an AI writes them, and later visits reuse the saved ones."
        >
          {(data) => <SpikeCards data={data} />}
        </Section>

        <ReasonCategories coverage={monthly.data?.coverage} />

        <NdcLookup />
      </main>

      <footer className="mx-auto max-w-6xl px-4 py-8 text-sm text-ink-2">
        <p>
          Data: the FDA's openFDA drug directory and enforcement reports. Only the newest recalls are loaded, and only about one recall in four names an NDC.
        </p>
      </footer>
    </div>
  )
}

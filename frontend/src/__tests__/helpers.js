import { vi } from 'vitest'

// Pretend API responses for the tests. The tests never touch a real server.
export function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// A pretend CSV download, with the header the real API sends so the page can read the file name.
export function csvResponse(body, filename) {
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': `attachment; filename="${filename}"` },
  })
}

// Replaces fetch. `handler(url)` returns a Response, or an Error to simulate "could not connect".
export function stubFetch(handler) {
  const fetchMock = vi.fn(async (url) => {
    const result = handler(String(url))
    if (result instanceof Error) throw result
    return result ?? jsonResponse({ detail: 'Not Found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export const networkDown = () => stubFetch(() => new TypeError('Failed to fetch'))

export const SPIKE_FACTS = {
  month: '2019-03',
  recalls: 535,
  baseline_mean: 96.58,
  baseline_stddev: 43.5,
  z_score: 10.08,
  top_reason_categories: [
    { category: 'Sterility / contamination', recalls: 494 },
    { category: 'Impurities', recalls: 25 },
    { category: 'Failed specifications', recalls: 8 },
  ],
  top_recalling_firms: [
    { recalling_firm: 'King Bio Inc.', recalls: 465 },
    { recalling_firm: 'Advanced Pharma Inc.', recalls: 19 },
  ],
  top_firm_share_pct: 87,
  driver: 'one_firm',
}

export const AI_SPIKE = {
  month: '2019-03',
  facts: SPIKE_FACTS,
  summary: 'In March 2019, there were 535 recalls. King Bio Inc. accounts for 87% of the month.',
  source: 'ai',
  fallback_reason: null,
  cached: false,
}

export const TEMPLATE_SPIKE = {
  ...AI_SPIKE,
  summary: 'March 2019 had 535 recalls, well above the usual 97 a month.',
  source: 'template',
  fallback_reason: 'the AI call failed: Hugging Face returned HTTP 402 (no remaining credits)',
}

export const MONTHLY = {
  coverage: {
    oldest_report_date: '2019-01-09',
    newest_report_date: '2019-04-24',
    first_full_month: '2019-02',
    excluded_oldest_month: '2019-01',
    newest_month_may_be_incomplete: true,
  },
  classifications: ['Class I', 'Class II', 'Class III', 'Not Yet Classified'],
  months: [
    { month: '2019-02', total: 100, by_classification: { 'Class I': 10, 'Class II': 80, 'Class III': 10, 'Not Yet Classified': 0 } },
    { month: '2019-03', total: 535, by_classification: { 'Class I': 60, 'Class II': 450, 'Class III': 25, 'Not Yet Classified': 0 } },
    { month: '2019-04', total: 90, by_classification: { 'Class I': 9, 'Class II': 70, 'Class III': 10, 'Not Yet Classified': 1 } },
  ],
}

export const ANALYTICS_SPIKES = {
  threshold: 2,
  baseline_months: 12,
  months_scored: 92,
  coverage: MONTHLY.coverage,
  spikes: [SPIKE_FACTS],
}

export const REASONS = {
  start: null,
  end: null,
  total: 9999,
  categories: [
    { category: 'Sterility / contamination', recalls: 4808, share: 0.4808 },
    { category: 'CGMP violations', recalls: 2265, share: 0.2265 },
    { category: 'Other', recalls: 250, share: 0.025 },
  ],
  other_share: 0.025,
  top_other_reasons: [{ reason: 'Temperature Abuse: product samples were stored too cold', recalls: 13 }],
}

export const RECALL_ITEM = {
  recall_number: 'D-0123-2026',
  recalling_firm: 'Acme Pharma',
  product_description: 'Acme tablets',
  reason_for_recall: 'Lack of Assurance of Sterility',
  classification: 'Class II',
  status: 'Ongoing',
  report_date: '2026-09-02',
}

// A router for the whole dashboard: every path the page asks for gets a realistic answer.
export function healthyApi(overrides = {}) {
  const routes = {
    '/health': () => jsonResponse({ status: 'ok', database: 'reachable' }),
    '/recalls?limit=1': () => jsonResponse({ total: 9999, limit: 1, offset: 0, items: [] }),
    '/recalls?classification=Class%20I&limit=1': () => jsonResponse({ total: 1175, limit: 1, offset: 0, items: [] }),
    '/analytics/recalls/monthly': () => jsonResponse(MONTHLY),
    '/analytics/recalls/spikes': () => jsonResponse(ANALYTICS_SPIKES),
    '/insights/recalls/spikes': () => jsonResponse({ model: 'test/model', spikes: [AI_SPIKE] }),
    '/analytics/recalls/reasons': () => jsonResponse(REASONS),
    ...overrides,
  }
  return (url) => (routes[url] ? routes[url]() : undefined)
}

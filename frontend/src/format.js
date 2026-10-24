// Small helpers that turn API values into readable text. Dates are formatted in UTC so the day never shifts
// with the viewer's time zone.

const integer = new Intl.NumberFormat('en-US')

export const formatInt = (n) => integer.format(n)

export const formatPercent = (fraction, digits = 1) => `${(fraction * 100).toFixed(digits)}%`

// '2018-02-21' -> '21 Feb 2018'
export function formatDate(iso) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

// A date and time in the viewer's own time zone, for "generated on" lines: '24 Oct 2026, 14:05'
export function formatDateTime(date) {
  return date.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// Says what a chosen date range means, in words: for the report note and the printed page.
export function describeRange(from, to) {
  if (from && to) return `reported from ${formatDate(from)} to ${formatDate(to)}`
  if (from) return `reported from ${formatDate(from)} onwards`
  if (to) return `reported up to ${formatDate(to)}`
  return 'all recalls in the loaded data'
}

// '2019-03' -> 'Mar 2019' (or 'March 2019' with style 'long')
export function formatMonth(month, style = 'short') {
  return new Date(`${month}-01T00:00:00Z`).toLocaleDateString('en-US', { month: style, year: 'numeric', timeZone: 'UTC' })
}

// 0, 500, 1.5K, 12K: for axis ticks
export function compactNumber(n) {
  if (n < 1000) return String(n)
  const thousands = n / 1000
  return `${Number.isInteger(thousands) ? thousands : thousands.toFixed(1)}K`
}

// The date a number of whole months before an ISO date, as an ISO date (for the "last 12 months" preset)
export function monthsBefore(iso, months) {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCMonth(d.getUTCMonth() - months)
  return d.toISOString().slice(0, 10)
}

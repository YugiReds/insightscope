import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import App from '../App.jsx'
import MonthlyChart from '../components/MonthlyChart.jsx'
import PrintHeader from '../components/PrintHeader.jsx'
import ReasonCategories from '../components/ReasonCategories.jsx'
import ReportBar, { recallsHref } from '../components/ReportBar.jsx'
import { SpikeCard } from '../components/SpikeCards.jsx'
import { ANALYTICS_SPIKES, MONTHLY, REASONS, TEMPLATE_SPIKE, csvResponse, healthyApi, jsonResponse, networkDown, stubFetch } from './helpers.js'

const NO_RANGE = { from: '', to: '', error: null }
const RANGE_2025 = { from: '2025-01-01', to: '2025-12-31', error: null }

// ---------------------------------------------------------------------------------------------------------
// The download links and the print button
// ---------------------------------------------------------------------------------------------------------

describe('the Download report area: links and print button', () => {
  it('has a link to each CSV file and a Print / Save as PDF button', () => {
    render(<ReportBar range={NO_RANGE} />)
    const recalls = screen.getByRole('link', { name: 'Download recalls (CSV)' })
    const spikes = screen.getByRole('link', { name: 'Download spike summaries (CSV)' })
    expect(recalls).toHaveAttribute('href', '/reports/recalls.csv')
    expect(spikes).toHaveAttribute('href', '/reports/spikes.csv')
    expect(recalls).toHaveAttribute('download')
    expect(spikes).toHaveAttribute('download')
    expect(screen.getByRole('button', { name: 'Print / Save as PDF' })).toBeInTheDocument()
  })

  it('the recalls link follows the date range, and the spike link does not', () => {
    render(<ReportBar range={RANGE_2025} />)
    expect(screen.getByRole('link', { name: 'Download recalls (CSV)' })).toHaveAttribute('href', '/reports/recalls.csv?start=2025-01-01&end=2025-12-31')
    expect(screen.getByRole('link', { name: 'Download spike summaries (CSV)' })).toHaveAttribute('href', '/reports/spikes.csv')
  })

  it('builds the address for a range with only a start, only an end, or neither', () => {
    expect(recallsHref({ from: '2025-01-01', to: '' })).toBe('/reports/recalls.csv?start=2025-01-01')
    expect(recallsHref({ from: '', to: '2025-12-31' })).toBe('/reports/recalls.csv?end=2025-12-31')
    expect(recallsHref({ from: '', to: '' })).toBe('/reports/recalls.csv')
  })

  it('says what each file covers', () => {
    render(<ReportBar range={RANGE_2025} />)
    const region = screen.getByRole('region', { name: 'Download report' })
    expect(region).toHaveTextContent('reported from 1 Jan 2025 to 31 Dec 2025')
    expect(region).toHaveTextContent('always covers every spike')
  })

  it('opens the browser print window when Print / Save as PDF is pressed', async () => {
    window.print = vi.fn()
    render(<ReportBar range={NO_RANGE} />)
    await userEvent.click(screen.getByRole('button', { name: 'Print / Save as PDF' }))
    expect(window.print).toHaveBeenCalledTimes(1)
  })

  it('does not offer the recalls file while the date range is invalid, and says why', () => {
    render(<ReportBar range={{ from: '2025-12-31', to: '2025-01-01', error: 'The "From" date must be on or before the "To" date.' }} />)
    expect(screen.queryByRole('link', { name: 'Download recalls (CSV)' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download recalls (CSV)' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Fix the date range')
    expect(screen.getByRole('link', { name: 'Download spike summaries (CSV)' })).toBeInTheDocument() // unaffected
  })
})

describe('downloading from the page', () => {
  let clicked
  beforeEach(() => {
    clicked = []
    URL.createObjectURL = vi.fn(() => 'blob:fake')
    URL.revokeObjectURL = vi.fn()
    // jsdom cannot really download. Record which file name the page asked for instead.
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      clicked.push({ name: this.download, href: this.href })
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it('fetches the file with the chosen range, saves it under the name the server chose, and confirms', async () => {
    const fetchMock = stubFetch((url) => (url.startsWith('/reports/recalls.csv') ? csvResponse('recall_number\r\nD-1\r\n', 'insightscope-recalls_2025-01-01_to_2025-12-31.csv') : undefined))
    render(<ReportBar range={RANGE_2025} />)
    await userEvent.click(screen.getByRole('link', { name: 'Download recalls (CSV)' }))

    expect(await screen.findByText('Downloaded insightscope-recalls_2025-01-01_to_2025-12-31.csv')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/reports/recalls.csv?start=2025-01-01&end=2025-12-31', expect.anything())
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(clicked).toEqual([{ name: 'insightscope-recalls_2025-01-01_to_2025-12-31.csv', href: 'blob:fake' }])
  })

  it('shows a preparing message while the spike file is made, and mentions the AI', async () => {
    let finish
    stubFetch(() => new Promise((resolve) => { finish = () => resolve(csvResponse('month\r\n', 'insightscope-spikes.csv')) }))
    render(<ReportBar range={NO_RANGE} />)
    await userEvent.click(screen.getByRole('link', { name: 'Download spike summaries (CSV)' }))
    expect(await screen.findByText(/Preparing the spike summaries file/)).toHaveTextContent('an AI writes the summaries')
    await act(async () => finish())
    expect(await screen.findByText('Downloaded insightscope-spikes.csv')).toBeInTheDocument()
  })

  it('says the API is unreachable, and Try again downloads it again', async () => {
    const fetchMock = networkDown()
    render(<ReportBar range={NO_RANGE} />)
    await userEvent.click(screen.getByRole('link', { name: 'Download recalls (CSV)' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("Can't reach the API")
    expect(clicked).toEqual([]) // nothing was saved
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it("shows the API's reason when it rejects the request (HTTP 422)", async () => {
    stubFetch(() => jsonResponse({ detail: 'start must not be later than end' }, 422))
    render(<ReportBar range={RANGE_2025} />)
    await userEvent.click(screen.getByRole('link', { name: 'Download recalls (CSV)' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The API returned an error (HTTP 422)')
    expect(alert).toHaveTextContent('start must not be later than end')
    expect(clicked).toEqual([])
  })

  it('tells a database outage apart from the API being down', async () => {
    stubFetch(() => jsonResponse({ detail: 'Database unavailable' }, 503))
    render(<ReportBar range={NO_RANGE} />)
    await userEvent.click(screen.getByRole('link', { name: 'Download spike summaries (CSV)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("The API can't reach its database")
  })
})

// ---------------------------------------------------------------------------------------------------------
// The printed page
// ---------------------------------------------------------------------------------------------------------

describe('the print-only title block', () => {
  afterEach(() => vi.useRealTimers())

  it('shows the title, the date generated, the data range and the reason-category range, and only on paper', () => {
    render(<PrintHeader coverage={MONTHLY.coverage} range={RANGE_2025} />)
    const header = screen.getByTestId('print-header')
    expect(header).toHaveTextContent('Recall report')
    expect(header).toHaveTextContent('Generated')
    expect(header).toHaveTextContent('9 Jan 2019 to 24 Apr 2019')
    expect(header).toHaveTextContent('reported from 1 Jan 2025 to 31 Dec 2025')
    expect(header).toHaveClass('hidden', 'print:block') // hidden on screen, shown on paper
  })

  it('says "all recalls" when no range is chosen, and copes with data that has not loaded', () => {
    render(<PrintHeader coverage={undefined} range={NO_RANGE} />)
    const header = screen.getByTestId('print-header')
    expect(header).toHaveTextContent('all recalls in the loaded data')
    expect(header).toHaveTextContent('Not available')
  })

  it('updates the generated time just before printing, so an old open page prints the real time', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-24T10:00:00'))
    render(<PrintHeader coverage={MONTHLY.coverage} range={NO_RANGE} />)
    expect(screen.getByTestId('print-header')).toHaveTextContent('24 Oct 2026, 10:00')
    vi.setSystemTime(new Date('2026-10-25T09:30:00'))
    act(() => {
      window.dispatchEvent(new Event('beforeprint'))
    })
    expect(screen.getByTestId('print-header')).toHaveTextContent('25 Oct 2026, 09:30')
  })
})

describe('what is hidden and what is kept when printing', () => {
  const hiddenInPrint = (element) => element.closest('[class~="print:hidden"]')

  async function loadedApp() {
    stubFetch((url) => (url.startsWith('/analytics/recalls/reasons') ? jsonResponse(REASONS) : healthyApi()(url)))
    render(<App />)
    await screen.findByText('9,999')
    await screen.findByTestId('chart-summary')
    await screen.findByRole('article', { name: 'March 2019' })
  }

  it('hides the header buttons, the download area, the lookup and the date picker', async () => {
    await loadedApp()
    expect(hiddenInPrint(screen.getByRole('link', { name: 'API docs' }))).not.toBeNull()
    expect(hiddenInPrint(screen.getByText('API and database OK'))).not.toBeNull()
    expect(hiddenInPrint(screen.getByRole('button', { name: 'Print / Save as PDF' }))).not.toBeNull()
    expect(hiddenInPrint(screen.getByRole('link', { name: 'Download recalls (CSV)' }))).not.toBeNull()
    expect(hiddenInPrint(screen.getByRole('button', { name: 'Check recalls' }))).not.toBeNull()
    expect(hiddenInPrint(screen.getByLabelText('From'))).not.toBeNull()
    expect(hiddenInPrint(screen.getByRole('button', { name: 'Last 12 months' }))).not.toBeNull()
  })

  it('keeps the headline numbers, the chart, the spike cards, the reason categories and the data limits', async () => {
    await loadedApp()
    expect(hiddenInPrint(screen.getByText('9,999'))).toBeNull()                                  // headline numbers
    expect(hiddenInPrint(screen.getByTestId('chart-summary'))).toBeNull()                        // the monthly chart's section
    expect(hiddenInPrint(screen.getByRole('article', { name: 'March 2019' }))).toBeNull()        // a spike card
    expect(hiddenInPrint(screen.getByText('AI'))).toBeNull()                                     // its badge
    expect(hiddenInPrint(screen.getByTestId('reasons-summary'))).toBeNull()                      // reason categories
    expect(hiddenInPrint(screen.getByText(/only about one recall in four names an NDC/))).toBeNull() // the data limits
  })

  it('has print-only lines: the report title, the range of the reasons, and the note about AI summaries', async () => {
    await loadedApp()
    expect(screen.getByTestId('print-header')).toBeInTheDocument()
    expect(screen.getByText('Recalls included: all recalls in the loaded data.')).toHaveClass('hidden', 'print:block')
    expect(screen.getByText(/Summaries marked AI were written by an AI model/)).toHaveClass('hidden', 'print:block')
  })

  it('writes out on paper why a template summary was used, because a hover tooltip cannot be printed', () => {
    render(<SpikeCard spike={TEMPLATE_SPIKE} model="m" />)
    const printed = screen.getByText(/Template summary\. Why the AI was not used:/)
    expect(printed).toHaveTextContent('no remaining credits')
    expect(printed).toHaveClass('hidden', 'print:block')
  })

  it('the date range chosen on the page flows into the download link and the printout', async () => {
    await loadedApp()
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2019-02-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2019-03-31' } })
    expect(screen.getByRole('link', { name: 'Download recalls (CSV)' })).toHaveAttribute('href', '/reports/recalls.csv?start=2019-02-01&end=2019-03-31')
    expect(screen.getByTestId('print-header')).toHaveTextContent('reported from 1 Feb 2019 to 31 Mar 2019')
    expect(screen.getByText('Recalls included: reported from 1 Feb 2019 to 31 Mar 2019.')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------------------
// Charts on paper. In a real print test the chart VANISHED: a stretchy chart cannot be trusted to resize itself in
// time for the print layout. So just before printing, charts switch to a fixed size, and back afterwards.
// ---------------------------------------------------------------------------------------------------------

describe('charts while printing', () => {
  const surface = (container) => container.querySelector('svg.recharts-surface')

  it('switches the monthly chart to a fixed size just before printing, and back afterwards', () => {
    const { container } = render(<MonthlyChart monthly={MONTHLY} spikes={{ data: ANALYTICS_SPIKES, error: null }} />)
    act(() => {
      window.dispatchEvent(new Event('beforeprint'))
    })
    expect(surface(container)).toHaveAttribute('width', '620')   // narrow enough for both Letter and A4
    expect(surface(container)).toHaveAttribute('height', '250')  // shorter than on screen, so more fits on a page
    act(() => {
      window.dispatchEvent(new Event('afterprint'))
    })
    expect(surface(container)?.getAttribute('width')).not.toBe('620') // back to stretching to fit the screen
  })

  it('does the same for the reason-categories chart', async () => {
    stubFetch(() => jsonResponse(REASONS))
    const { container } = render(<ReasonCategories coverage={MONTHLY.coverage} />)
    await screen.findByTestId('reasons-summary')
    act(() => {
      window.dispatchEvent(new Event('beforeprint'))
    })
    expect(surface(container)).toHaveAttribute('width', '620')
    expect(surface(container)).toHaveAttribute('height', String(REASONS.categories.length * 30 + 16)) // 30 px a row on paper
  })

  it('keeps the chart legend and the text summary while printing', () => {
    render(<MonthlyChart monthly={MONTHLY} spikes={{ data: ANALYTICS_SPIKES, error: null }} />)
    act(() => {
      window.dispatchEvent(new Event('beforeprint'))
    })
    expect(screen.getByRole('list', { name: 'Chart legend' })).toHaveTextContent('Spike month')
    expect(screen.getByTestId('chart-summary')).toHaveTextContent('The busiest month was Mar 2019')
  })
})

// ---------------------------------------------------------------------------------------------------------
// The print stylesheet itself (jsdom does not apply CSS, so these read the file)
// ---------------------------------------------------------------------------------------------------------

describe('the stylesheet', () => {
  // npm test runs from the frontend folder, so this is frontend/src/index.css
  const css = readFileSync(resolve(process.cwd(), 'src', 'index.css'), 'utf8')

  it('applies the dark colours on SCREEN only, so a printout is light even when the screen is dark', () => {
    expect(css).toMatch(/@media screen and \(prefers-color-scheme: dark\)/)
    expect(css).not.toMatch(/@media \(prefers-color-scheme: dark\)/)
  })

  it('has print rules that keep colours, avoid splitting cards, and hide the screen-only folds', () => {
    const print = css.slice(css.indexOf('@media print'))
    expect(print).toMatch(/print-color-adjust:\s*exact/)
    expect(print).toMatch(/break-inside:\s*avoid/)
    expect(print).toMatch(/details\s*{\s*display:\s*none/)
  })

  it('does not force whole sections onto one page, and does not shrink the chart wrapper to nothing', () => {
    const print = css.slice(css.indexOf('@media print'))
    // A tall section that must stay in one piece just leaves a big blank gap. Cards, charts and rows still stay whole.
    expect(print).not.toMatch(/section,\s*article/)
    expect(print).toMatch(/article,\s*figure,\s*tr\s*{\s*break-inside:\s*avoid/)
    // This rule once collapsed the printed chart to zero width, because the chart draws inside a zero-width box.
    expect(print).not.toMatch(/recharts-wrapper\s*{[^}]*max-width/)
  })

  it('makes the text smaller on paper, so more fits on each page', () => {
    const print = css.slice(css.indexOf('@media print'))
    expect(print).toMatch(/html\s*{\s*font-size:\s*12\.5px/)
  })
})

import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MonthlyChart, { summarizeMonthly } from '../components/MonthlyChart.jsx'
import ReasonCategories, { summarizeReasons } from '../components/ReasonCategories.jsx'
import { ApiError } from '../api.js'
import { ANALYTICS_SPIKES, MONTHLY, REASONS, jsonResponse, stubFetch } from './helpers.js'

describe('monthly chart: text alternatives', () => {
  const spikes = { data: ANALYTICS_SPIKES, error: null }

  it('describes the chart in words, including the busiest month and the spike months', () => {
    render(<MonthlyChart monthly={MONTHLY} spikes={spikes} />)
    const summary = screen.getByTestId('chart-summary')
    expect(summary).toHaveTextContent('Recalls per month from Feb 2019 to Apr 2019 (3 months)')
    expect(summary).toHaveTextContent('The busiest month was Mar 2019 with 535 recalls')
    expect(summary).toHaveTextContent('1 months are marked as spikes: Mar 2019')
    expect(summary).toHaveTextContent('Class II')
  })

  it('has a table twin with every month, every class and the spike flag', () => {
    render(<MonthlyChart monthly={MONTHLY} spikes={spikes} />)
    const table = screen.getByRole('table', { name: 'Recalls per month by classification' })
    expect(within(table).getAllByRole('row')).toHaveLength(4) // header + 3 months
    const march = within(table).getByRole('row', { name: /Mar 2019/ })
    expect(march).toHaveTextContent('Spike')
    expect(march).toHaveTextContent('535')
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Month', 'Spike', 'Total', 'Class I', 'Class II', 'Class III', 'Not Yet Classified',
    ])
  })

  it('has a legend that includes the spike marker, so colour is never the only key', () => {
    render(<MonthlyChart monthly={MONTHLY} spikes={spikes} />)
    const legend = screen.getByRole('list', { name: 'Chart legend' })
    expect(legend).toHaveTextContent('Class I')
    expect(legend).toHaveTextContent('(most serious)')
    expect(legend).toHaveTextContent('Spike month')
  })

  it('says so when spike markers could not be loaded, and still shows the chart', () => {
    render(<MonthlyChart monthly={MONTHLY} spikes={{ data: null, error: new ApiError('network', 'Could not connect to the API.') }} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Spike markers could not be loaded')
    expect(screen.getByTestId('chart-summary')).toHaveTextContent('No spike months are marked')
  })
})

describe('summarizeMonthly', () => {
  it('handles no data', () => {
    expect(summarizeMonthly({ months: [], classifications: [] })).toBe('There is no monthly data to chart yet.')
  })

  it('orders the class shares by severity and rounds a tiny share to "under 1%"', () => {
    const text = summarizeMonthly(MONTHLY)
    expect(text.indexOf('Class I ')).toBeLessThan(text.indexOf('Class II '))
    expect(text).toContain('Not Yet Classified under 1%')
  })
})

describe('reason categories', () => {
  const coverage = MONTHLY.coverage

  it('summarises the chart in words and offers a table', async () => {
    stubFetch((url) => (url === '/analytics/recalls/reasons' ? jsonResponse(REASONS) : undefined))
    render(<ReasonCategories coverage={coverage} />)
    expect(await screen.findByTestId('reasons-summary')).toHaveTextContent('Of 9,999 recalls, Sterility / contamination is the largest reason (48.1%)')
    expect(screen.getByTestId('reasons-summary')).toHaveTextContent('"Other"')
    const table = screen.getByRole('table', { name: 'Recalls by reason category' })
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    expect(screen.getByText(/Temperature Abuse/)).toBeInTheDocument() // what is inside "Other"
  })

  it('has labelled date inputs', () => {
    stubFetch(() => new Promise(() => {}))
    render(<ReasonCategories coverage={coverage} />)
    expect(screen.getByLabelText('From')).toHaveAttribute('type', 'date')
    expect(screen.getByLabelText('To')).toHaveAttribute('type', 'date')
  })

  it('sends the chosen dates to the API', async () => {
    const fetchMock = stubFetch(() => jsonResponse(REASONS))
    render(<ReasonCategories coverage={coverage} />)
    await screen.findByTestId('reasons-summary')
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2019-02-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2019-03-31' } })
    await screen.findByText(/Showing recalls reported from 1 Feb 2019 to 31 Mar 2019/)
    expect(fetchMock).toHaveBeenCalledWith('/analytics/recalls/reasons?start=2019-02-01&end=2019-03-31', expect.anything())
  })

  it('catches a backwards range with a clear message and does not call the API with it', async () => {
    const fetchMock = stubFetch(() => jsonResponse(REASONS))
    render(<ReasonCategories coverage={coverage} />)
    await screen.findByTestId('reasons-summary')
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2019-04-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2019-02-01' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('The "From" date must be on or before the "To" date.')
    expect(screen.getByLabelText('From')).toHaveAttribute('aria-invalid', 'true')
    const urls = fetchMock.mock.calls.map(([u]) => u)
    expect(urls.some((u) => u.includes('start=2019-04-01&end=2019-02-01'))).toBe(false)
  })

  it('presets fill the date boxes relative to the newest report', async () => {
    stubFetch(() => jsonResponse(REASONS))
    const user = userEvent.setup()
    render(<ReasonCategories coverage={coverage} />)
    await screen.findByTestId('reasons-summary')
    await user.click(screen.getByRole('button', { name: 'Last 12 months' }))
    expect(screen.getByLabelText('From')).toHaveValue('2018-04-24')
    expect(screen.getByLabelText('To')).toHaveValue('2019-04-24')
    expect(screen.getByRole('button', { name: 'Last 12 months' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows a clear error when the API rejects the request', async () => {
    stubFetch(() => jsonResponse({ detail: 'start must not be later than end' }, 422))
    render(<ReasonCategories coverage={coverage} />)
    const section = await screen.findByRole('region', { name: 'Why drugs are recalled' })
    expect(await within(section).findByText('The API returned an error (HTTP 422)')).toBeInTheDocument()
    expect(within(section).getByText('start must not be later than end')).toBeInTheDocument()
  })

  it('summarizeReasons copes with an empty range', () => {
    expect(summarizeReasons({ total: 0, categories: [], other_share: 0 })).toBe('There are no recalls in this date range.')
  })
})

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import App from '../App.jsx'
import { ApiError } from '../api.js'
import { Section } from '../components/States.jsx'
import { healthyApi, jsonResponse, networkDown, stubFetch } from './helpers.js'

// The support-engineer part: when something is down, the page must say WHAT is down in plain words, never go blank.

describe('when the API is down', () => {
  it('says so plainly in the header, a banner and every section, and never goes blank', async () => {
    networkDown()
    render(<App />)

    expect(await screen.findByText('API unreachable')).toBeInTheDocument()
    expect(await screen.findByText('The InsightScope API is not answering.')).toBeInTheDocument()

    // the page is still there: title and all section headings
    expect(screen.getByRole('heading', { level: 1, name: 'InsightScope' })).toBeInTheDocument()
    for (const name of ['Recalls per month', 'Spike months', 'Why drugs are recalled', 'Has this drug been recalled?']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    }

    // every data section explains the problem and offers a retry
    const monthly = screen.getByRole('region', { name: 'Recalls per month' })
    expect(await within(monthly).findByText("Can't reach the API")).toBeInTheDocument()
    expect(within(monthly).getByText(/Check that the API server is running/)).toBeInTheDocument()
    expect(within(monthly).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    const spikes = screen.getByRole('region', { name: 'Spike months' })
    expect(await within(spikes).findByText("Can't reach the API")).toBeInTheDocument()
  })

  it('also marks each summary tile as unavailable instead of leaving it empty', async () => {
    networkDown()
    render(<App />)
    const summary = screen.getByRole('region', { name: 'Summary' })
    expect(await within(summary).findAllByText('Unavailable')).toHaveLength(4)
  })
})

describe('when the API is up but its database is down', () => {
  it('tells that apart from the API being down', async () => {
    stubFetch(() => jsonResponse({ detail: 'Database unavailable' }, 503))
    render(<App />)

    expect(await screen.findByText('API is up, database unavailable')).toBeInTheDocument()
    expect(screen.queryByText('API unreachable')).not.toBeInTheDocument()
    expect(await screen.findByText('The API is running, but it cannot reach its database.')).toBeInTheDocument()
    const monthly = screen.getByRole('region', { name: 'Recalls per month' })
    expect(await within(monthly).findByText("The API can't reach its database")).toBeInTheDocument()
  })
})

describe('when everything works', () => {
  it('shows OK in the header and real numbers', async () => {
    stubFetch(healthyApi())
    render(<App />)
    expect(await screen.findByText('API and database OK')).toBeInTheDocument()
    expect(await screen.findByText('9,999')).toBeInTheDocument() // total recalls tile
    expect(await screen.findByText('11.8%')).toBeInTheDocument() // 1,175 of 9,999
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a loading message first, not a blank card', () => {
    stubFetch(() => new Promise(() => {})) // never answers
    render(<App />)
    expect(screen.getByText('Loading monthly recall counts…')).toBeInTheDocument()
  })
})

describe('Section states', () => {
  const state = (overrides) => ({ data: null, error: null, loading: false, reload: vi.fn(), ...overrides })

  it('shows the error and calls reload when Try again is pressed', async () => {
    const reload = vi.fn()
    render(
      <Section id="x" title="Example" state={state({ error: new ApiError('network', 'Could not connect to the API.'), reload })}>
        {() => <p>content</p>}
      </Section>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent("Can't reach the API")
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(reload).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('content')).not.toBeInTheDocument()
  })

  it('keeps the old content and says the refresh failed', () => {
    render(
      <Section id="x" title="Example" state={state({ data: { ok: true }, error: new ApiError('http', 'HTTP 500', { status: 500 }) })}>
        {() => <p>content</p>}
      </Section>,
    )
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Could not refresh')
    expect(screen.getByText('Showing the last data that loaded.')).toBeInTheDocument()
  })

  it('dims content while it reloads instead of replacing it with a skeleton', () => {
    render(
      <Section id="x" title="Example" state={state({ data: { ok: true }, loading: true })}>
        {() => <p>content</p>}
      </Section>,
    )
    expect(screen.getByText('content').parentElement).toHaveAttribute('aria-busy', 'true')
  })
})

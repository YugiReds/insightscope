import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NdcLookup from '../components/NdcLookup.jsx'
import { RECALL_ITEM, jsonResponse, networkDown, stubFetch } from './helpers.js'

async function lookup(value) {
  const user = userEvent.setup()
  render(<NdcLookup />)
  await user.type(screen.getByLabelText('NDC'), value)
  await user.click(screen.getByRole('button', { name: 'Check recalls' }))
  return user
}

describe('the NDC lookup has four clearly different outcomes', () => {
  it('1. found: lists the recalls that name the NDC', async () => {
    const fetchMock = stubFetch((url) =>
      url === '/products/16729-455/recalls?limit=25'
        ? jsonResponse({ product_ndc: '16729-455', total: 26, limit: 25, offset: 0, items: [RECALL_ITEM, { ...RECALL_ITEM, recall_number: 'D-0124-2026' }] })
        : undefined,
    )
    await lookup('16729-455')

    const result = await screen.findByRole('region', { name: 'Recalls for 16729-455' })
    expect(result).toHaveTextContent('26 recalls list NDC 16729-455')
    expect(within(result).getByText('D-0123-2026')).toBeInTheDocument()
    expect(within(result).getAllByRole('row')).toHaveLength(3) // header + 2 recalls
    expect(within(result).getByRole('button', { name: 'Show 24 more' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/products/16729-455/recalls?limit=25', expect.anything())
    // and none of the other outcomes
    expect(screen.queryByText(/No recalls found/)).not.toBeInTheDocument()
    expect(screen.queryByText(/valid NDC/)).not.toBeInTheDocument()
  })

  it('2. none: a valid NDC with no recalls is a calm notice that does NOT claim it was never recalled', async () => {
    stubFetch((url) => (url.startsWith('/products/99999-999/recalls') ? jsonResponse({ product_ndc: '99999-999', total: 0, limit: 25, offset: 0, items: [] }) : undefined))
    await lookup('99999-999')

    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('No recalls found for 99999-999')
    expect(notice).toHaveTextContent('does not prove it was never recalled')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument() // it is information, not an error
    expect(screen.queryByText(/valid NDC/)).not.toBeInTheDocument()
  })

  it('3. invalid: a malformed NDC shows what the API rejected (HTTP 422) and the right format', async () => {
    stubFetch((url) =>
      url.startsWith('/products/abc/recalls')
        ? jsonResponse({ detail: [{ loc: ['path', 'ndc'], msg: "String should match pattern '^\\d{4,5}-\\d{1,4}$'" }] }, 422)
        : undefined,
    )
    await lookup('abc')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('That does not look like a valid NDC')
    expect(alert).toHaveTextContent('rejected “abc” (HTTP 422)')
    expect(alert).toHaveTextContent('String should match pattern')
    expect(alert).toHaveTextContent('for example 16729-455')
    expect(screen.queryByText(/No recalls found/)).not.toBeInTheDocument() // a typo must never look like good news
  })

  it('4. error: when the API cannot be reached it says so, with a Try again button', async () => {
    networkDown()
    await lookup('16729-455')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("Can't reach the API")
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByText(/valid NDC/)).not.toBeInTheDocument()
    expect(screen.queryByText(/No recalls found/)).not.toBeInTheDocument()
  })

  it('shows a database outage as an error, not as "no recalls"', async () => {
    stubFetch(() => jsonResponse({ detail: 'Database unavailable' }, 503))
    await lookup('16729-455')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("The API can't reach its database")
    expect(screen.queryByText(/No recalls found/)).not.toBeInTheDocument()
  })
})

describe('the NDC lookup form', () => {
  it('has a labelled input and a format hint tied to it', () => {
    render(<NdcLookup />)
    const input = screen.getByLabelText('NDC')
    expect(input).toHaveAccessibleDescription(/4 or 5 digits, a hyphen, then 1 to 4 digits/)
  })

  it('asks for an NDC instead of searching when the box is empty', async () => {
    const fetchMock = stubFetch(() => undefined)
    const user = userEvent.setup()
    render(<NdcLookup />)
    await user.click(screen.getByRole('button', { name: 'Check recalls' }))
    expect(await screen.findByText('Type an NDC first')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('the example buttons fill the box and search', async () => {
    stubFetch((url) => (url.startsWith('/products/99999-999/recalls') ? jsonResponse({ product_ndc: '99999-999', total: 0, limit: 25, offset: 0, items: [] }) : undefined))
    const user = userEvent.setup()
    render(<NdcLookup />)
    await user.click(screen.getByRole('button', { name: /99999-999 \(no recalls\)/ }))
    expect(screen.getByLabelText('NDC')).toHaveValue('99999-999')
    expect(await screen.findByText('No recalls found for 99999-999')).toBeInTheDocument()
  })

  it('loads the next page when Show more is pressed', async () => {
    const page1 = Array.from({ length: 25 }, (_, i) => ({ ...RECALL_ITEM, recall_number: `D-${String(i).padStart(4, '0')}-2026` }))
    const page2 = [{ ...RECALL_ITEM, recall_number: 'D-9999-2026' }]
    stubFetch((url) => {
      if (url === '/products/16729-455/recalls?limit=25') return jsonResponse({ product_ndc: '16729-455', total: 26, limit: 25, offset: 0, items: page1 })
      if (url === '/products/16729-455/recalls?limit=25&offset=25') return jsonResponse({ product_ndc: '16729-455', total: 26, limit: 25, offset: 25, items: page2 })
      return undefined
    })
    const user = await lookup('16729-455')
    await user.click(await screen.findByRole('button', { name: 'Show 1 more' }))
    expect(await screen.findByText('D-9999-2026')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Recalls for 16729-455' })).toHaveTextContent('Showing 26 of 26')
    expect(screen.queryByRole('button', { name: /Show .* more/ })).not.toBeInTheDocument()
  })
})

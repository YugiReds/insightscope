import { render, screen } from '@testing-library/react'
import { SourceBadge, SpikeCard } from '../components/SpikeCards.jsx'
import { AI_SPIKE, TEMPLATE_SPIKE } from './helpers.js'

describe('the AI / Template badge', () => {
  it('says AI, and explains on hover that the numbers were checked', () => {
    render(<SourceBadge source="ai" reason={null} model="test/model" />)
    const badge = screen.getByText('AI')
    expect(badge).toHaveAttribute('data-source', 'ai')
    expect(badge.getAttribute('title')).toMatch(/Written by an AI model \(test\/model\)/)
    expect(badge.getAttribute('title')).toMatch(/checked against those facts/)
    expect(badge.getAttribute('title')).not.toMatch(/Why the AI was not used/)
  })

  it('says Template, and gives the fallback reason on hover', () => {
    const reason = 'the AI call failed: Hugging Face returned HTTP 402 (no remaining credits)'
    render(<SourceBadge source="template" reason={reason} />)
    const badge = screen.getByText('Template')
    expect(badge).toHaveAttribute('data-source', 'template')
    expect(badge).toHaveAttribute('title', `Why the AI was not used: ${reason}`)
  })

  it('also gives the reason to screen readers, and can be reached with the keyboard', () => {
    render(<SourceBadge source="template" reason="HF_TOKEN is not set, so the AI was not called" />)
    const badge = screen.getByText('Template')
    expect(badge).toHaveAttribute('aria-label', expect.stringContaining('HF_TOKEN is not set'))
    expect(badge).toHaveAttribute('tabindex', '0')
  })

  it('looks different for AI and Template, so they are not told apart by the word alone', () => {
    const { rerender } = render(<SourceBadge source="ai" />)
    const aiClass = screen.getByText('AI').className
    rerender(<SourceBadge source="template" reason="x" />)
    expect(screen.getByText('Template').className).not.toBe(aiClass)
  })

  it('still says why when the API gave no reason', () => {
    render(<SourceBadge source="template" reason={null} />)
    expect(screen.getByText('Template').getAttribute('title')).toMatch(/no reason was given/)
  })
})

describe('a spike card', () => {
  it('shows the month, the count against the usual level, the top firm and its share, and the summary', () => {
    render(<SpikeCard spike={AI_SPIKE} model="test/model" />)
    const card = screen.getByRole('article', { name: 'March 2019' })
    expect(card).toHaveTextContent('535') // recalls
    expect(card).toHaveTextContent('97') // usual level (96.58 rounded)
    expect(card).toHaveTextContent('z-score 10.1')
    expect(card).toHaveTextContent('King Bio Inc.')
    expect(card).toHaveTextContent('465 recalls, 87% of the month')
    expect(card).toHaveTextContent("Mainly one firm's mass recall")
    expect(card).toHaveTextContent(AI_SPIKE.summary)
    expect(screen.getByText('AI')).toBeInTheDocument()
  })

  it('shows the Template badge and its reason on a template card', () => {
    render(<SpikeCard spike={TEMPLATE_SPIKE} model="test/model" />)
    expect(screen.getByText('Template')).toHaveAttribute('title', expect.stringContaining('no remaining credits'))
    expect(screen.queryByText('AI')).not.toBeInTheDocument()
  })

  it('says when an AI summary was reused from the cache', () => {
    render(<SpikeCard spike={{ ...AI_SPIKE, cached: true }} model="m" />)
    expect(screen.getByText('Saved summary (reused from the cache)')).toBeInTheDocument()
  })
})

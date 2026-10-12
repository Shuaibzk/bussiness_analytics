import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import KpiCard from './KpiCard'
import { Reveal, Words } from './Reveal'
import { Badge, Segmented } from './ui'
import { FilterProvider, useFilters } from '../lib/filters'

describe('KpiCard', () => {
  const card = { key: 'revenue', label: 'Net revenue', fmt: 'currency', value: 3845611, delta: { pct: 12.5 }, spark: [1, 2, 3], good_direction: 'up' }
  it('shows the label, a compact value and the change', () => {
    render(<KpiCard card={card} />)
    expect(screen.getByText('Net revenue')).toBeInTheDocument()
    expect(screen.getByText('$3.8M')).toBeInTheDocument()
    expect(screen.getByText(/12\.5%/)).toBeInTheDocument()
  })
  it('colours a rise in a "lower is better" metric as bad', () => {
    render(<KpiCard card={{ ...card, key: 'return_rate', label: 'Return rate', fmt: 'percent', value: 18.6, delta: { abs: 2 }, good_direction: 'down' }} />)
    const badge = screen.getByText(/2 pp/)
    expect(badge.className).toMatch(/rose/)
  })
})

describe('Words / Reveal', () => {
  it('renders every word as its own animated span, separated by real spaces so text can wrap', () => {
    const { container } = render(<h1><Words text="Analytics that know who is asking" /></h1>)
    const spans = container.querySelectorAll('span[style*="inline-block"]')
    expect(spans).toHaveLength(6)
    expect(container.textContent).toBe('Analytics that know who is asking')
    expect(spans[1].style.transition).toContain('85ms') // second word: default stagger 85ms
  })
  it('Reveal renders its children', () => {
    render(<Reveal>hello</Reveal>)
    expect(screen.getByText('hello')).toBeInTheDocument()
  })
})

describe('Segmented', () => {
  it('marks the active option with aria-pressed and reports changes', () => {
    const onChange = vi.fn()
    render(<Segmented label="Basis" value="net" onChange={onChange} options={[{ value: 'net', label: 'Net' }, { value: 'gross', label: 'Gross' }]} />)
    expect(screen.getByRole('button', { name: 'Net' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Gross' })).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Gross' }))
    expect(onChange).toHaveBeenCalledWith('gross')
  })
})

describe('Badge', () => {
  it('renders children', () => {
    render(<Badge tone="good">Active</Badge>)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })
})

function Probe() {
  const { filters, basis } = useFilters()
  return <pre data-testid="out">{JSON.stringify({ filters, basis })}</pre>
}

describe('FilterProvider (filters live in the URL)', () => {
  it('parses multi-value filters, numeric years, ISO dates and the basis from the query string', () => {
    render(
      <MemoryRouter initialEntries={['/?year=2023&year=2024&region=Asia&region=Europe&date_from=2023-01-01&basis=gross']}>
        <FilterProvider><Probe /></FilterProvider>
      </MemoryRouter>,
    )
    const out = JSON.parse(screen.getByTestId('out').textContent)
    expect(out.filters.year).toEqual([2023, 2024])
    expect(out.filters.region).toEqual(['Asia', 'Europe'])
    expect(out.filters.date_from).toBe('2023-01-01')
    expect(out.basis).toBe('gross')
  })
  it('ignores malformed dates and unknown parameters', () => {
    render(
      <MemoryRouter initialEntries={['/?date_from=not-a-date&evil=1&date_to=2024-02-30x']}>
        <FilterProvider><Probe /></FilterProvider>
      </MemoryRouter>,
    )
    const out = JSON.parse(screen.getByTestId('out').textContent)
    expect(out.filters).toEqual({})
    expect(out.basis).toBe('net')
  })
})

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router'
import { formatMoney, formatNumber, formatRatio } from '@/lib/format'
import { inGroup } from '@/lib/verdicts'
import { filterPriorities } from '@/features/priorities/filter'
import type { PriorityRow } from '@/features/priorities/api'
import { Figure } from '@/ui/Figure'
import { RouteError } from '@/app/RouteError'

describe('formatting', () => {
  it('uses Indian grouping and crore/lakh for rupees', () => {
    expect(formatNumber(1234567)).toBe('12,34,567')
    expect(formatMoney(53_500_000, 'INR', '₹')).toBe('₹5.35 crore')
    expect(formatMoney(250_000, 'INR', '₹')).toBe('₹2.5 lakh')
    expect(formatMoney(null, 'INR', '₹')).toBe('—')
    expect(formatRatio(71.34)).toBe('71.3×')
  })
})

describe('action groups', () => {
  it('audit covers both delivery gaps and stalled money', () => {
    expect(inGroup('DELIVERY_GAP', 'audit')).toBe(true)
    expect(inGroup('STALLED_ALLOCATION', 'audit')).toBe(true)
    expect(inGroup('UNSERVED_GAP', 'audit')).toBe(false)
    expect(inGroup('MONITOR', 'all')).toBe(true)
  })
})

function row(id: number, verdict: PriorityRow['verdict'], name: string, parent: string, sector = 'water'): PriorityRow {
  return {
    id, rank: id, verdict, score: 50, sector, sector_label: sector, distinct_reporters: 10, report_count: 10,
    per_1000: 1, baseline_ratio: 2, is_emerging: false, avg_urgency: 3, estimated_cost: null, beneficiaries: null,
    summary: '', summary_source: 'template', region: { id: String(id), name, level_name: 'block', parent_name: parent },
  }
}

describe('priority filters', () => {
  const items = [
    row(1, 'UNSERVED_GAP', 'Kalasa', 'Chikkamagaluru'),
    row(2, 'DELIVERY_GAP', 'Malur', 'Kolar'),
    row(3, 'DEMAND_HOTSPOT', 'Dandeli', 'Uttara Kannada', 'road'),
  ]
  it('filters by group, need and place search (including the parent area)', () => {
    expect(filterPriorities(items, { group: 'fund', need: '', q: '' }).map((p) => p.id)).toEqual([1])
    expect(filterPriorities(items, { group: 'all', need: 'road', q: '' }).map((p) => p.id)).toEqual([3])
    expect(filterPriorities(items, { group: 'all', need: '', q: 'kolar' }).map((p) => p.id)).toEqual([2])
  })
})

describe('Figure', () => {
  it('attaches the source to a number', () => {
    render(<Figure source={{ name: 'Jal Jeevan Mission', period: '2026', url: 'https://example.org' }}>66.6%</Figure>)
    expect(screen.getByText('66.6%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Source: Jal Jeevan Mission · 2026' })).toBeInTheDocument()
  })

  it('shows a plain number when there is no source', () => {
    render(<Figure>12</Figure>)
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('error isolation', () => {
  it('a crashing page shows an error inside the layout; the navigation survives', async () => {
    function Boom(): never {
      throw new Error('map exploded')
    }
    const router = createMemoryRouter(
      [{
        element: <div><nav>Sidebar</nav><Outlet /></div>,
        children: [{ path: '/map', element: <Boom />, errorElement: <RouteError /> }],
      }],
      { initialEntries: ['/map'] },
    )
    render(<RouterProvider router={router} />)
    expect(await screen.findByText('This page hit an error')).toBeInTheDocument()
    expect(screen.getByText('map exploded')).toBeInTheDocument()
    expect(screen.getByText('Sidebar')).toBeInTheDocument()
  })
})

import { useQuery } from '@tanstack/react-query'
import { get, type Verdict } from '@/lib/api'
import { withRegion } from '@/lib/regions'

export interface Overview {
  country_code: string
  region: { id: string; name: string } | null
  run: { id: number; completed_at: string } | null
  reports: {
    total: number
    located: number
    unlocated: number | null // null when scoped to a region: unlocated reports belong to no place
    awaiting_processing: number
    flagged_coordinated: number
    synthetic: number
  }
  languages: { code: string; count: number }[]
  channels: { channel: string; count: number }[]
  regions_covered: number
  verdicts: Partial<Record<Verdict, number>>
  emerging: number
}

export interface TopPriority {
  id: number
  rank: number
  verdict: Verdict
  score: number
  region: { name: string; parent_name: string | null }
  sector_label: string
  distinct_reporters: number
  is_emerging: boolean
}

export interface Rollup {
  parent: { id: string; name: string } | null
  path: { id: string; name: string }[]
  level_name: string | null
  items: {
    id: string
    name: string
    has_children: boolean
    places_needing_action: number
    verdicts: Partial<Record<Verdict, number>>
  }[]
}

export interface Unlocated {
  total: number
  reasons: { reason: string; count: number }[]
}

export function useOverview(region: string) {
  return useQuery({
    queryKey: ['overview', region],
    queryFn: () => get<Overview>(withRegion('/api/v1/overview', region)),
  })
}

export function useTopPriorities(region: string) {
  return useQuery({
    queryKey: ['priorities', 'top', region],
    queryFn: () => get<{ items: TopPriority[] }>(withRegion('/api/v1/priorities?limit=8', region)),
  })
}

export function useRollup(region: string) {
  return useQuery({ queryKey: ['rollup', region], queryFn: () => get<Rollup>(withRegion('/api/v1/rollup', region)) })
}

export function useUnlocated(enabled: boolean) {
  return useQuery({ queryKey: ['unlocated'], queryFn: () => get<Unlocated>('/api/v1/unlocated'), enabled })
}

import { useQuery } from '@tanstack/react-query'
import { get, type Verdict } from '@/lib/api'

export interface Overview {
  country_code: string
  run: { id: number; completed_at: string } | null
  reports: {
    total: number
    located: number
    unlocated: number
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

export function useOverview() {
  return useQuery({ queryKey: ['overview'], queryFn: () => get<Overview>('/api/v1/overview') })
}

export function useTopPriorities() {
  return useQuery({
    queryKey: ['priorities', 'top'],
    queryFn: () => get<{ items: TopPriority[] }>('/api/v1/priorities?limit=8'),
  })
}

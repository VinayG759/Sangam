import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { get, type Verdict } from '@/lib/api'
import { withRegion } from '@/lib/regions'

export interface Analytics {
  run: { id: number; completed_at: string } | null
  region: { id: string; name: string } | null
  currency: string
  currency_symbol: string
  totals: {
    reports: number
    residents: number
    places_needing_action: number
    money_flagged: number
    money_flagged_synthetic: boolean
  }
  timeline: { week: string; reports: number }[]
  needs: { sector: string; label: string; verdicts: Partial<Record<Verdict, number>> }[]
  money: { status: string; projects: number; amount: number; synthetic: boolean }[]
  progress: {
    sector: string
    label: string
    statistic: string
    unit: string | null
    served_threshold: number | null
    synthetic: boolean
    baseline_period: string | null
    current_period: string | null
    source_name: string | null
    rows: { id: string; name: string; places: number; baseline: number; current: number }[]
  }[]
}

export interface ImpactProjects {
  projects: { label: string }[]
}

export function useAnalytics(region: string) {
  return useQuery({
    queryKey: ['analytics', region],
    queryFn: () => get<Analytics>(withRegion('/api/v1/analytics', region)),
    placeholderData: keepPreviousData, // hold the last render while a new region loads
  })
}

export function useImpactProjects() {
  return useQuery({ queryKey: ['impact', 'projects'], queryFn: () => get<ImpactProjects>('/api/v1/impact/projects') })
}

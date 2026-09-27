import { useQuery } from '@tanstack/react-query'
import { get, type Fact, type Verdict } from '@/lib/api'

export interface PriorityRow {
  id: number
  rank: number
  verdict: Verdict
  score: number
  region: { id: string; name: string; level_name: string | null; parent_name: string | null }
  sector: string
  sector_label: string
  distinct_reporters: number
  report_count: number
  per_1000: number | null
  baseline_ratio: number | null
  is_emerging: boolean
  avg_urgency: number | null
  estimated_cost: number | null
  beneficiaries: number | null
  summary: string
  summary_source: 'model' | 'template'
}

export interface Component {
  value: number
  weight: number
  contribution: number
}

export interface PriorityDetail extends PriorityRow {
  components: Record<string, Component> & { missing?: string[] }
  evidence: Fact[]
  run_id: number
  first_seen: string
  last_seen: string
  weights: Record<string, number>
}

export interface SourceReport {
  created_at: string
  channel: string
  language: string | null
  text_original: string | null
  text_en: string | null
  urgency: number | null
  is_synthetic: boolean
}

export function usePriorities() {
  return useQuery({
    queryKey: ['priorities', 'all'],
    queryFn: () => get<{ run: { id: number; completed_at: string } | null; items: PriorityRow[] }>('/api/v1/priorities?limit=500'),
  })
}

export function usePriority(id: string) {
  return useQuery({ queryKey: ['priority', id], queryFn: () => get<PriorityDetail>(`/api/v1/priorities/${id}`) })
}

export function useSourceReports(id: string) {
  return useQuery({ queryKey: ['priority', id, 'reports'], queryFn: () => get<SourceReport[]>(`/api/v1/priorities/${id}/reports`) })
}

// ─────────────────────────────────────────────────────────────────────────────
// Sangam API Client
// Typed wrappers for all backend endpoints.
// Base URL comes from VITE_API_URL env var or defaults to same-origin (via proxy).
// ─────────────────────────────────────────────────────────────────────────────

const BASE = ((import.meta as unknown) as Record<string, unknown> & { env?: Record<string, string> }).env?.VITE_API_URL ?? '';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface OverviewData {
  total_citizen_reports: number;
  total_sanctioned_expenditure: number;
  unserved_gaps_count: number;
  stalled_projects_count: number;
  stalled_capital_amount: number;
  sectors_breakdown: Record<string, number>;
}

export interface Priority {
  id: number;
  cluster_id: number;
  title: string;
  sector: string;
  score: number;
  verdict: 'UNSERVED_GAP' | 'STALLED_ALLOCATION' | 'UNDERFUNDED_CRITICAL' | 'DELIVERY_GAP' | 'WELL_SERVED';
  report_count: number;
  region_name: string;
  details: Record<string, unknown> | null;
  list_type: 'fund' | 'audit';
}

export interface NarrativeBrief {
  summary: string;
  why_prioritized: string;
  fiscal_gap_analysis: string;
  recommended_action: string;
}

export interface PriorityDetail {
  id: number;
  score: number;
  verdict: string;
  evidence_bundle: Record<string, unknown>;
  narrative_brief: NarrativeBrief;
}

export interface Report {
  id: number;
  raw_text: string;
  detected_language: string;
  english_translation: string;
  sector: string;
  specific_issue: string;
  urgency_score: number;
  sentiment: string;
  pii_redacted_text: string;
  cluster_id: number | null;
  reported_at: string | null;
}

export interface ReportList {
  total: number;
  limit: number;
  offset: number;
  reports: Report[];
}

export interface SimulationAllocation {
  cluster_id: number;
  title: string;
  sector: string;
  allocated_amount: number;
  pct_funded: number;
  status: 'fully_funded' | 'partially_funded';
}

export interface SimulationResult {
  strategy: string;
  simulated_budget: number;
  total_spent: number;
  remaining_budget: number;
  gaps_fully_resolved: number;
  citizen_needs_addressed: number;
  allocations: SimulationAllocation[];
}

export interface PackInfo {
  country_code: string;
  region_name: string;
  languages: Array<{ code: string; name: string; is_default: boolean }>;
  sectors: Array<{ key: string; name: string }>;
  weights: {
    demand_density: number;
    vulnerability_index: number;
    expenditure_gap: number;
    urgency: number;
  };
}

export interface Cluster {
  id: number;
  title: string;
  sector: string;
  region_id: number;
  region_name: string;
  report_count: number;
  created_at: string | null;
  centroid: string | null;
  is_approximate_location: boolean;
  priority: { id: number; score: number; verdict: string } | null;
}

// ── API functions ─────────────────────────────────────────────────────────────

export const api = {
  overview: () => get<OverviewData>('/api/v1/overview'),

  priorities: (sector?: string, verdict?: string) => {
    const params = new URLSearchParams();
    if (sector) params.set('sector', sector);
    if (verdict) params.set('verdict', verdict);
    const qs = params.toString();
    return get<Priority[]>(`/api/v1/priorities${qs ? `?${qs}` : ''}`);
  },

  priorityDetail: (id: number) => get<PriorityDetail>(`/api/v1/priorities/${id}`),

  reports: (params?: { sector?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.sector) qs.set('sector', params.sector);
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    return get<ReportList>(`/api/v1/reports${qs.toString() ? `?${qs}` : ''}`);
  },

  clusters: (sector?: string) => {
    const qs = sector ? `?sector=${encodeURIComponent(sector)}` : '';
    return get<Cluster[]>(`/api/v1/clusters${qs}`);
  },

  pack: () => get<PackInfo>('/api/v1/pack'),

  simulate: (available_budget: number, strategy: string) =>
    post<SimulationResult>('/api/v1/simulate', { available_budget, strategy }),

  submitCitizenReport: (data: FormData) => {
    return fetch(`${BASE}/api/v1/ingest/citizen`, {
      method: 'POST',
      body: data
    }).then(res => {
      if (!res.ok) throw new Error(`POST /api/v1/ingest/citizen failed: ${res.status}`);
      return res.json() as Promise<{ tracking_id: string; [key: string]: any }>;
    })
  },

  checkStatus: (trackingId: string) => get<Record<string, unknown>>(`/api/v1/citizens/${encodeURIComponent(trackingId)}`),
};

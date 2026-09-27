// The one fetch client. Feature folders define their own queries on top of it.

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`
}

export async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(apiUrl(path)))
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function postForm<T>(path: string, form: FormData): Promise<T> {
  return handle<T>(await fetch(apiUrl(path), { method: 'POST', body: form }))
}

// ── Shared response shapes ──────────────────────────────────────────────────

export type Verdict = 'UNSERVED_GAP' | 'DELIVERY_GAP' | 'STALLED_ALLOCATION' | 'DEMAND_HOTSPOT' | 'MONITOR'

export interface Need {
  key: string
  label: string
  labels: Record<string, string>
}

export interface Pack {
  country_code: string
  country_name: string
  currency: string
  currency_symbol: string
  languages: string[]
  admin_levels: string[]
  population_label: string
  min_distinct_reporters: number
  weights: Record<string, number>
  needs: Need[]
  features: { simulator: boolean; export: boolean; web_intake: boolean }
}

export interface Fact {
  id: string
  label: string
  value: number | null
  unit: string | null
  period?: string | null
  source_name: string | null
  source_url: string | null
}

export interface Region {
  id: string
  name: string
  level: number
  parent_id: string | null
}

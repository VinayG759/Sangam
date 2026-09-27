import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { get, type Region } from './api'

/** Every place below country level. Loaded once and cached for the session. */
export function useRegions() {
  return useQuery({ queryKey: ['regions'], queryFn: () => get<Region[]>('/api/v1/regions'), staleTime: Infinity })
}

/** Places in tree order (each parent followed by its children), with their depth. */
export function treeOrder(regions: Region[]): (Region & { depth: number })[] {
  const ids = new Set(regions.map((r) => r.id))
  const children = new Map<string | null, Region[]>()
  for (const r of regions) {
    const parent = r.parent_id && ids.has(r.parent_id) ? r.parent_id : null
    children.set(parent, [...(children.get(parent) ?? []), r])
  }
  const out: (Region & { depth: number })[] = []
  const walk = (parent: string | null, depth: number) => {
    for (const r of (children.get(parent) ?? []).sort((a, b) => a.name.localeCompare(b.name))) {
      out.push({ ...r, depth })
      walk(r.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
}

/** The region the page is scoped to, kept in the URL (?region=) so a view can be shared. */
export function useRegionParam(): [string, (id: string) => void] {
  const [params, setParams] = useSearchParams()
  const region = params.get('region') ?? ''
  const setRegion = (id: string) => {
    const next = new URLSearchParams(params)
    if (id) next.set('region', id)
    else next.delete('region')
    setParams(next, { replace: true })
  }
  return [region, setRegion]
}

/** Append the current region to a link, so moving between pages keeps the scope. */
export function withRegion(path: string, region: string): string {
  if (!region) return path
  return `${path}${path.includes('?') ? '&' : '?'}region=${encodeURIComponent(region)}`
}

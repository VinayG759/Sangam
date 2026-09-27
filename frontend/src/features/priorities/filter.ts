import { type ActionGroup, inGroup } from '@/lib/verdicts'
import type { PriorityRow } from './api'

export interface PriorityFilter {
  group: ActionGroup
  need: string
  q: string
}

export function filterPriorities(items: PriorityRow[], { group, need, q }: PriorityFilter): PriorityRow[] {
  const needle = q.trim().toLowerCase()
  return items.filter(
    (p) =>
      inGroup(p.verdict, group) &&
      (!need || p.sector === need) &&
      (!needle ||
        p.region.name.toLowerCase().includes(needle) ||
        (p.region.parent_name ?? '').toLowerCase().includes(needle)),
  )
}

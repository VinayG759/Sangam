import type { Region } from '@/lib/api'
import { usePack } from '@/lib/pack'
import { useRegions } from '@/lib/regions'
import { inputStyle } from './primitives'

/**
 * One dropdown per level, linked: choose a district, then (optionally) a block inside it.
 * A level with a single place (one state loaded) is skipped, so the first choice is a real one.
 */
export function RegionPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const pack = usePack()
  const regions = useRegions()
  const all = regions.data ?? []
  const byId = new Map(all.map((r) => [r.id, r]))
  const children = new Map<string, Region[]>()
  for (const r of all) {
    const parent = r.parent_id && byId.has(r.parent_id) ? r.parent_id : ''
    children.set(parent, [...(children.get(parent) ?? []), r])
  }
  for (const list of children.values()) list.sort((a, b) => a.name.localeCompare(b.name))

  // Skip down through levels that have only one place.
  let start = ''
  while ((children.get(start) ?? []).length === 1 && children.has(children.get(start)![0].id)) {
    start = children.get(start)![0].id
  }
  const startName = start ? byId.get(start)?.name : pack.data?.country_name

  // The chosen place's ancestors below `start`, top first.
  const path: string[] = []
  for (let id = value; id && id !== start && byId.has(id); id = byId.get(id)!.parent_id ?? '') path.unshift(id)

  const levels: { parent: string; selected: string }[] = [{ parent: start, selected: path[0] ?? '' }]
  path.forEach((id, i) => {
    if ((children.get(id) ?? []).length) levels.push({ parent: id, selected: path[i + 1] ?? '' })
  })

  const levelName = (parent: string) => {
    const first = children.get(parent)?.[0]
    const name = first ? pack.data?.admin_levels[first.level] : undefined
    return name ? name[0].toUpperCase() + name.slice(1) : 'Place'
  }

  return (
    <div className="flex flex-wrap gap-2">
      {levels.map(({ parent, selected }) => (
        <select
          key={parent || 'root'}
          aria-label={levelName(parent)}
          className={`${inputStyle} w-full min-w-0 sm:w-44`}
          value={selected}
          disabled={regions.isPending}
          onChange={(e) => onChange(e.target.value || (parent === start ? '' : parent))}
        >
          <option value="">
            {parent === start
              ? `All of ${startName ?? 'the country'}`
              : `All of ${byId.get(parent)?.name ?? ''}`}
          </option>
          {(children.get(parent) ?? []).map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      ))}
    </div>
  )
}

import { usePack } from '@/lib/pack'
import { treeOrder, useRegions } from '@/lib/regions'
import { inputStyle } from './primitives'

/** One dropdown for the whole tree; deeper places are indented under their parent. */
export function RegionPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const pack = usePack()
  const regions = useRegions()
  const ordered = treeOrder(regions.data ?? [])
  const levelName = (level: number) => pack.data?.admin_levels[level]

  return (
    <select
      aria-label="Region"
      className={`${inputStyle} max-w-64`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={regions.isPending}
    >
      <option value="">All of {pack.data?.country_name ?? 'the country'}</option>
      {ordered.map((r) => (
        <option key={r.id} value={r.id}>
          {'  '.repeat(r.depth)}
          {r.name}
          {r.depth === 0 && levelName(r.level) ? ` (${levelName(r.level)})` : ''}
        </option>
      ))}
    </select>
  )
}

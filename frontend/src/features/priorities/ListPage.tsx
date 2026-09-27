import { Link, useNavigate, useSearchParams } from 'react-router'
import { Search, TrendingUp } from 'lucide-react'
import { formatNumber, formatRatio } from '@/lib/format'
import { usePack } from '@/lib/pack'
import { ACTION_GROUPS, type ActionGroup, inGroup } from '@/lib/verdicts'
import { inputStyle, PageHeader, Segmented } from '@/ui/primitives'
import { EmptyState, ErrorState, Skeleton } from '@/ui/states'
import { VerdictBadge } from '@/ui/VerdictBadge'
import { usePriorities } from './api'
import { filterPriorities } from './filter'

export default function PrioritiesPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const pack = usePack()
  const query = usePriorities()

  const group = (params.get('group') as ActionGroup) || 'all'
  const need = params.get('need') ?? ''
  const q = params.get('q') ?? ''

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value && value !== 'all') next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const items = query.data?.items ?? []
  const shown = filterPriorities(items, { group, need, q })
  const maxScore = Math.max(1, ...items.map((p) => p.score))

  return (
    <>
      <PageHeader
        title="Priorities"
        description="Every place and need with enough residents reporting, ranked. Places needing action come first; within them, the score orders them. The score is arithmetic you can check — open any row to see it."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented
          label="Action"
          value={group}
          onChange={(value) => update('group', value)}
          options={ACTION_GROUPS.map((g) => ({
            value: g.key,
            label: (
              <>
                {g.label}
                <span className="num ml-1.5 text-faint">{items.filter((p) => inGroup(p.verdict, g.key)).length}</span>
              </>
            ),
          }))}
        />
        <select aria-label="Need" className={inputStyle} value={need} onChange={(e) => update('need', e.target.value)}>
          <option value="">All needs</option>
          {pack.data?.needs.map((n) => (
            <option key={n.key} value={n.key}>{n.label}</option>
          ))}
        </select>
        <label className="relative">
          <span className="sr-only">Search places</span>
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-faint" />
          <input className={`${inputStyle} w-56 pl-8`} placeholder="Search a place" value={q} onChange={(e) => update('q', e.target.value)} />
        </label>
      </div>

      {query.isPending ? (
        <div className="space-y-2">{[...Array(10)].map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.run ? (
        <EmptyState title="No analysis has run yet" />
      ) : shown.length === 0 ? (
        <EmptyState title="Nothing matches these filters" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[760px] text-left">
            <thead className="text-[12px] text-faint">
              <tr className="border-b border-line">
                <th className="px-4 py-2.5 font-normal">#</th>
                <th className="px-2 py-2.5 font-normal">Place</th>
                <th className="px-2 py-2.5 font-normal">Need</th>
                <th className="px-2 py-2.5 font-normal">Verdict</th>
                <th className="px-2 py-2.5 text-right font-normal">Residents</th>
                <th className="px-2 py-2.5 text-right font-normal" title="Reports per head compared with the median place for this need">vs typical</th>
                <th className="w-40 px-4 py-2.5 font-normal">Score</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => navigate(`/priorities/${p.id}`)}
                  className="cursor-pointer border-b border-line last:border-0 hover:bg-subtle"
                >
                  <td className="num px-4 py-2.5 text-faint">{p.rank}</td>
                  <td className="px-2 py-2.5">
                    <Link to={`/priorities/${p.id}`} onClick={(e) => e.stopPropagation()} className="font-medium hover:text-accent">
                      {p.region.name}
                    </Link>
                    <span className="ml-1.5 text-[12px] text-faint">
                      {[p.region.level_name, p.region.parent_name].filter(Boolean).join(' · ')}
                    </span>
                    {p.is_emerging && (
                      <span title="Complaints accelerating" className="ml-2 inline-flex items-center gap-0.5 text-[11px] text-delivery">
                        <TrendingUp className="size-3" /> emerging
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2.5 text-muted">{p.sector_label}</td>
                  <td className="px-2 py-2.5"><VerdictBadge verdict={p.verdict} /></td>
                  <td className="num px-2 py-2.5 text-right">{formatNumber(p.distinct_reporters)}</td>
                  <td className="num px-2 py-2.5 text-right text-muted">{formatRatio(p.baseline_ratio)}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="h-1.5 flex-1 rounded-full bg-subtle">
                        <span className="block h-1.5 rounded-full bg-ink/60" style={{ width: `${Math.max(2, (p.score / maxScore) * 100)}%` }} />
                      </span>
                      <span className="num w-9 text-right text-[12px]">{formatNumber(p.score, 1)}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {query.data?.run && (
        <p className="mt-3 text-[12px] text-faint">
          Showing {shown.length} of {items.length}. Places with fewer than {pack.data?.min_distinct_reporters ?? 5} distinct
          residents reporting are never shown, to protect the people who report — they still count toward the typical level.
        </p>
      )}
    </>
  )
}

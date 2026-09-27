import { Link, useNavigate } from 'react-router'
import { ChevronRight, TrendingUp } from 'lucide-react'
import type { Verdict } from '@/lib/api'
import { formatDateTime, formatNumber, languageName } from '@/lib/format'
import { usePack } from '@/lib/pack'
import { useRegionParam, withRegion } from '@/lib/regions'
import { VERDICT_ORDER, VERDICTS } from '@/lib/verdicts'
import { PageHeader, Panel, Stat } from '@/ui/primitives'
import { RegionPicker } from '@/ui/RegionPicker'
import { EmptyState, ErrorState, Skeleton } from '@/ui/states'
import { VerdictBadge } from '@/ui/VerdictBadge'
import { type Rollup, useOverview, useRollup, useTopPriorities, useUnlocated } from './api'

const CHANNEL_NAMES: Record<string, string> = { whatsapp: 'WhatsApp', telegram: 'Telegram', web: 'Web form', seed: 'Seeded' }

const UNLOCATED_REASONS: Record<string, string> = {
  no_place_named: 'No place mentioned',
  place_not_recognised: 'Place not recognised',
  low_confidence_match: 'Place match too uncertain',
  gave_up_after_questions: 'Still unclear after follow-up questions',
  awaiting_place: 'Waiting for the resident to name the place',
  awaiting_confirmation: 'Waiting for the resident to confirm the place',
  not_recorded: 'Reason not recorded (older reports)',
}

export default function OverviewPage() {
  const [region, setRegion] = useRegionParam()
  const overview = useOverview(region)
  const top = useTopPriorities(region)

  if (overview.isPending) return <OverviewSkeleton />
  if (overview.isError) return <ErrorState error={overview.error} />
  const data = overview.data
  const v = data.verdicts
  const audit = (v.DELIVERY_GAP ?? 0) + (v.STALLED_ALLOCATION ?? 0) + (v.PLANNED_NOT_STARTED ?? 0)
  const needAction = (v.UNSERVED_GAP ?? 0) + audit
  const to = (path: string) => withRegion(path, region)

  return (
    <>
      <PageHeader
        title={data.region ? `Overview · ${data.region.name}` : 'Overview'}
        description={
          data.run
            ? <>Where citizen demand and official data disagree. Analysis completed {formatDateTime(data.run.completed_at)}.</>
            : 'Where citizen demand and official data disagree.'
        }
        actions={<RegionPicker value={region} onChange={setRegion} />}
      />

      {!data.run ? (
        <EmptyState title="No analysis has run yet">
          Reports are being collected. Once an administrator runs the analysis, ranked priorities appear here.
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Places needing action" value={formatNumber(needAction)} hint="Fund or audit" to={to('/priorities')} />
            <Stat label="Unserved gaps" value={formatNumber(v.UNSERVED_GAP ?? 0)} hint="Recommend for funding" to={to('/priorities?group=fund')} />
            <Stat
              label="Audit recommended"
              value={formatNumber(audit)}
              hint="Delivery gaps, and money stalled or not started"
              to={to('/priorities?group=audit')}
            />
            <Stat label="Demand hotspots" value={formatNumber(v.DEMAND_HOTSPOT ?? 0)} hint="Verify — no official data yet" to={to('/priorities?group=verify')} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2 lg:self-start">
              <Panel
                title="Top priorities"
                actions={<Link to={to('/priorities')} className="text-[12px] text-accent">View all</Link>}
                flush
              >
                {top.isPending ? (
                  <div className="space-y-2 p-4">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-8" />)}</div>
                ) : top.isError ? (
                  <div className="p-4"><ErrorState error={top.error} /></div>
                ) : (
                  <table className="w-full text-left">
                    <thead className="text-[12px] text-faint">
                      <tr className="border-b border-line">
                        <th className="px-4 py-2 font-normal">#</th>
                        <th className="px-2 py-2 font-normal">Place</th>
                        <th className="px-2 py-2 font-normal">Need</th>
                        <th className="px-2 py-2 font-normal">Verdict</th>
                        <th className="px-4 py-2 text-right font-normal">Residents</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top.data.items.map((p) => (
                        <tr key={p.id} className="border-b border-line last:border-0 hover:bg-subtle">
                          <td className="num px-4 py-2 text-faint">{p.rank}</td>
                          <td className="px-2 py-2">
                            <Link to={`/priorities/${p.id}`} className="font-medium hover:text-accent">{p.region.name}</Link>
                            {p.region.parent_name && <span className="ml-1.5 text-[12px] text-faint">{p.region.parent_name}</span>}
                          </td>
                          <td className="px-2 py-2 text-muted">{p.sector_label}</td>
                          <td className="px-2 py-2"><VerdictBadge verdict={p.verdict} /></td>
                          <td className="num px-4 py-2 text-right">{formatNumber(p.distinct_reporters)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Panel>

              <RollupPanel region={region} onSelect={setRegion} />
            </div>

            <div className="space-y-6">
              <Panel title="Reach">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                  <Metric label="Citizen reports" value={formatNumber(data.reports.total)} />
                  <Metric label="Places reporting" value={formatNumber(data.regions_covered)} />
                  <Metric label="Languages" value={formatNumber(data.languages.length)} />
                  {data.reports.unlocated !== null && (
                    <Metric
                      label="Could not be placed"
                      value={formatNumber(data.reports.unlocated)}
                      hint="Counted, not mapped"
                    />
                  )}
                  {data.emerging > 0 && (
                    <Metric
                      label={<span className="inline-flex items-center gap-1"><TrendingUp className="size-3" /> Emerging</span>}
                      value={formatNumber(data.emerging)}
                      hint="Complaints accelerating"
                    />
                  )}
                  {data.reports.flagged_coordinated > 0 && (
                    <Metric label="Held for review" value={formatNumber(data.reports.flagged_coordinated)} hint="Possibly coordinated" />
                  )}
                </dl>
              </Panel>

              {data.reports.unlocated !== null && <UnlocatedPanel />}

              <Panel title="Languages received">
                <Bars rows={data.languages.map((l) => ({ label: languageName(l.code), value: l.count }))} />
              </Panel>

              <Panel title="Channels">
                <Bars rows={data.channels.map((c) => ({ label: CHANNEL_NAMES[c.channel] ?? c.channel, value: c.count }))} />
              </Panel>
            </div>
          </div>
        </>
      )}
    </>
  )
}

function RollupPanel({ region, onSelect }: { region: string; onSelect: (id: string) => void }) {
  const rollup = useRollup(region)
  const navigate = useNavigate()
  if (rollup.isPending) return <Skeleton className="h-64" />
  if (rollup.isError) return <ErrorState error={rollup.error} />
  const data = rollup.data
  if (!data.parent || data.items.length === 0) return null
  const max = Math.max(1, ...data.items.map((i) => total(i.verdicts)))

  return (
    <Panel
      title={<>Where action is needed{data.level_name ? `, by ${data.level_name}` : ''}</>}
      actions={<Breadcrumb path={data.path} onSelect={onSelect} />}
      flush
    >
      <table className="w-full text-left">
        <thead className="text-[12px] text-faint">
          <tr className="border-b border-line">
            <th className="px-4 py-2 font-normal">Place</th>
            <th className="px-2 py-2 text-right font-normal" title="Places inside with at least one fund or audit verdict">Need action</th>
            <th className="w-2/5 px-4 py-2 font-normal">Verdicts shown</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => (
            <tr
              key={item.id}
              onClick={() => (item.has_children ? onSelect(item.id) : navigate(withRegion('/priorities', item.id)))}
              className="cursor-pointer border-b border-line last:border-0 hover:bg-subtle"
            >
              <td className="px-4 py-2 font-medium">{item.name}</td>
              <td className="num px-2 py-2 text-right">{formatNumber(item.places_needing_action)}</td>
              <td className="px-4 py-2"><VerdictBar verdicts={item.verdicts} max={max} /></td>
              <td className="pr-3 text-faint"><ChevronRight className="size-4" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  )
}

function Breadcrumb({ path, onSelect }: { path: Rollup['path']; onSelect: (id: string) => void }) {
  const pack = usePack()
  return (
    <nav aria-label="Region path" className="flex flex-wrap items-center gap-1 text-[12px] text-muted">
      <button type="button" className="hover:text-accent" onClick={() => onSelect('')}>
        {pack.data?.country_name ?? 'Country'}
      </button>
      {path.map((p) => (
        <span key={p.id} className="inline-flex items-center gap-1">
          <ChevronRight className="size-3 text-faint" />
          <button type="button" className="hover:text-accent" onClick={() => onSelect(p.id)}>{p.name}</button>
        </span>
      ))}
    </nav>
  )
}

function total(verdicts: Partial<Record<Verdict, number>>): number {
  return Object.values(verdicts).reduce((sum, n) => sum + (n ?? 0), 0)
}

function VerdictBar({ verdicts, max }: { verdicts: Partial<Record<Verdict, number>>; max: number }) {
  const sum = total(verdicts)
  if (!sum) return <span className="text-[12px] text-faint" title="No place and need here has enough distinct residents reporting to be shown">None shown</span>
  const label = VERDICT_ORDER.filter((v) => verdicts[v]).map((v) => `${VERDICTS[v].label}: ${verdicts[v]}`).join(', ')
  return (
    <div className="flex items-center gap-2" title={label}>
      <span className="flex h-2 overflow-hidden rounded-full bg-subtle" style={{ width: `${(sum / max) * 100}%` }}>
        {VERDICT_ORDER.filter((v) => verdicts[v]).map((v) => (
          <span key={v} style={{ width: `${((verdicts[v] ?? 0) / sum) * 100}%`, background: VERDICTS[v].hex }} />
        ))}
      </span>
      <span className="num text-[12px] text-muted">{formatNumber(sum)}</span>
    </div>
  )
}

function UnlocatedPanel() {
  const pack = usePack()
  const unlocated = useUnlocated(true)
  if (unlocated.isPending) return <Skeleton className="h-32" />
  if (unlocated.isError) return <ErrorState error={unlocated.error} />
  return (
    <Panel title="Why reports could not be placed">
      {unlocated.data.total === 0 ? (
        <p className="text-muted">Every report so far has been placed on the map.</p>
      ) : (
        <Bars rows={unlocated.data.reasons.map((r) => ({ label: UNLOCATED_REASONS[r.reason] ?? r.reason, value: r.count }))} wide />
      )}
      <p className="mt-3 text-[11px] text-faint">
        Counts only. Report text is shown only where at least {pack.data?.min_distinct_reporters ?? 5} different
        residents report the same need in the same place. These reports have no place, so their text is never shown.
      </p>
    </Panel>
  )
}

function Metric({ label, value, hint }: { label: React.ReactNode; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="num text-lg font-semibold">{value}</dd>
      {hint && <dd className="text-[11px] text-faint">{hint}</dd>}
    </div>
  )
}

function Bars({ rows, wide }: { rows: { label: string; value: number }[]; wide?: boolean }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  if (!rows.length) return <p className="text-muted">None yet.</p>
  return (
    <ul className="space-y-2">
      {rows.map((row) => (
        <li
          key={row.label}
          className={`grid items-center gap-2 text-[13px] ${wide ? 'grid-cols-[1fr_4rem_2.5rem]' : 'grid-cols-[6rem_1fr_3.5rem]'}`}
        >
          <span className={wide ? 'text-muted' : 'truncate text-muted'}>{row.label}</span>
          <span className="h-1.5 rounded-full bg-subtle">
            <span className="block h-1.5 rounded-full bg-accent" style={{ width: `${(row.value / max) * 100}%` }} />
          </span>
          <span className="num text-right">{formatNumber(row.value)}</span>
        </li>
      ))}
    </ul>
  )
}

function OverviewSkeleton() {
  return (
    <>
      <Skeleton className="mb-6 h-10 w-72" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      <Skeleton className="mt-6 h-80" />
    </>
  )
}

import { Link } from 'react-router'
import { TrendingUp } from 'lucide-react'
import { formatDateTime, formatNumber, languageName } from '@/lib/format'
import { PageHeader, Panel, Stat } from '@/ui/primitives'
import { EmptyState, ErrorState, Skeleton } from '@/ui/states'
import { VerdictBadge } from '@/ui/VerdictBadge'
import { useOverview, useTopPriorities } from './api'

const CHANNEL_NAMES: Record<string, string> = { whatsapp: 'WhatsApp', telegram: 'Telegram', web: 'Web form', seed: 'Seeded' }

export default function OverviewPage() {
  const overview = useOverview()
  const top = useTopPriorities()

  if (overview.isPending) return <OverviewSkeleton />
  if (overview.isError) return <ErrorState error={overview.error} />
  const data = overview.data
  const v = data.verdicts
  const needAction = (v.UNSERVED_GAP ?? 0) + (v.DELIVERY_GAP ?? 0) + (v.STALLED_ALLOCATION ?? 0)

  return (
    <>
      <PageHeader
        title="Overview"
        description={
          data.run
            ? <>Where citizen demand and official data disagree. Analysis completed {formatDateTime(data.run.completed_at)}.</>
            : 'Where citizen demand and official data disagree.'
        }
      />

      {!data.run ? (
        <EmptyState title="No analysis has run yet">
          Reports are being collected. Once an administrator runs the analysis, ranked priorities appear here.
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Places needing action" value={formatNumber(needAction)} hint="Fund or audit" to="/priorities" />
            <Stat label="Unserved gaps" value={formatNumber(v.UNSERVED_GAP ?? 0)} hint="Recommend for funding" to="/priorities?group=fund" />
            <Stat
              label="Delivery gaps & stalled money"
              value={formatNumber((v.DELIVERY_GAP ?? 0) + (v.STALLED_ALLOCATION ?? 0))}
              hint="Recommend an audit"
              to="/priorities?group=audit"
            />
            <Stat label="Demand hotspots" value={formatNumber(v.DEMAND_HOTSPOT ?? 0)} hint="Verify — no official data yet" to="/priorities?group=verify" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Panel
              title="Top priorities"
              actions={<Link to="/priorities" className="text-[12px] text-accent">View all</Link>}
              className="lg:col-span-2 lg:self-start"
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

            <div className="space-y-6">
              <Panel title="Reach">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                  <Metric label="Citizen reports" value={formatNumber(data.reports.total)} />
                  <Metric label="Places reporting" value={formatNumber(data.regions_covered)} />
                  <Metric label="Languages" value={formatNumber(data.languages.length)} />
                  <Metric
                    label="Could not be placed"
                    value={formatNumber(data.reports.unlocated)}
                    hint="Counted, not mapped"
                  />
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

function Metric({ label, value, hint }: { label: React.ReactNode; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="num text-lg font-semibold">{value}</dd>
      {hint && <dd className="text-[11px] text-faint">{hint}</dd>}
    </div>
  )
}

function Bars({ rows }: { rows: { label: string; value: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  if (!rows.length) return <p className="text-muted">None yet.</p>
  return (
    <ul className="space-y-2">
      {rows.map((row) => (
        <li key={row.label} className="grid grid-cols-[6rem_1fr_3.5rem] items-center gap-2 text-[13px]">
          <span className="truncate text-muted">{row.label}</span>
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

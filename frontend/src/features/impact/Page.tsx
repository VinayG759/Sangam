import { useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { get } from '@/lib/api'
import { cx } from '@/lib/cx'
import { formatDate, formatMoney, formatNumber } from '@/lib/format'
import { Figure } from '@/ui/Figure'
import { PageHeader, Panel, Segmented } from '@/ui/primitives'
import { EmptyState, ErrorState, Skeleton } from '@/ui/states'

type ProgressLabel = 'NOT_REACHING' | 'STILL_SHORT' | 'NO_MAJOR_COMPLAINTS'

interface ProgressRow {
  region_id: string
  region_name: string
  parent_name: string | null
  level_name: string | null
  baseline: number
  baseline_period: string
  current: number
  current_period: string
  change: number
  label: ProgressLabel
  priority_id: number | null
  residents_reporting: number | null
}

interface Programme {
  sector: string
  sector_label: string
  statistic: string
  unit: string | null
  served_threshold: number | null
  source_name: string | null
  source_url: string | null
  rows: ProgressRow[]
}

interface ProjectRow {
  project_id: string
  title: string
  region_name: string
  sector_label: string
  completion_date: string
  amount: number | null
  currency: string | null
  source_name: string | null
  source_url: string | null
  reporters_before: number | null
  reporters_after: number | null
  change: number | null
  label: 'IMPROVED' | 'NO_CHANGE' | 'WORSENED' | 'INSUFFICIENT_DATA' | 'TOO_EARLY'
}

const PROGRESS: Record<ProgressLabel, { label: string; className: string; explain: string }> = {
  NOT_REACHING: {
    label: 'Not reaching people',
    className: 'bg-delivery-soft text-delivery',
    explain: 'Official data says served, yet many residents report the problem.',
  },
  STILL_SHORT: {
    label: 'Still short',
    className: 'bg-unserved-soft text-unserved',
    explain: 'Below the served level, and many residents report the problem.',
  },
  NO_MAJOR_COMPLAINTS: {
    label: 'No major complaints',
    className: 'bg-monitor-soft text-monitor',
    explain: 'Demand near the typical place, or too few reports to show.',
  },
}

const PROJECT_LABELS: Record<ProjectRow['label'], string> = {
  IMPROVED: 'Complaints fell after completion',
  NO_CHANGE: 'No clear change',
  WORSENED: 'Complaints rose after completion',
  INSUFFICIENT_DATA: 'Too few reports to tell',
  TOO_EARLY: 'Too early to tell',
}

export default function ImpactPage() {
  const progress = useQuery({ queryKey: ['impact', 'progress'], queryFn: () => get<{ programmes: Programme[] }>('/api/v1/impact/progress') })
  const projects = useQuery({
    queryKey: ['impact', 'projects'],
    queryFn: () => get<{ window_days: number; grace_days: number; has_project_data: boolean; projects: ProjectRow[] }>('/api/v1/impact/projects'),
  })
  const [filter, setFilter] = useState<'all' | ProgressLabel>('all')

  return (
    <>
      <PageHeader
        title="Impact"
        description="Is public investment reaching people? Official progress is set against what residents report today. Sangam shows what changed alongside what people say — it does not claim one caused the other."
      />

      {progress.isPending ? (
        <Skeleton className="h-96" />
      ) : progress.isError ? (
        <ErrorState error={progress.error} />
      ) : progress.data.programmes.length === 0 ? (
        <EmptyState title="No programme has a baseline statistic yet" />
      ) : (
        progress.data.programmes.map((programme) => {
          const counts = programme.rows.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.label]: (acc[r.label] ?? 0) + 1 }), {})
          const rows = programme.rows.filter((r) => filter === 'all' || r.label === filter)
          const source = { name: programme.source_name, url: programme.source_url }
          return (
            <Panel
              key={programme.sector}
              title={`${programme.sector_label}: official progress vs what residents say`}
              className="mb-6"
              flush
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
                <p className="max-w-2xl text-[13px] text-muted">
                  {programme.statistic}, from {programme.rows[0]?.baseline_period} to {programme.rows[0]?.current_period}
                  {programme.served_threshold !== null && <> · counted as served at {programme.served_threshold}%</>}.
                </p>
                <Segmented
                  label="Show"
                  value={filter}
                  onChange={setFilter}
                  options={[
                    { value: 'all', label: `All ${programme.rows.length}` },
                    ...(Object.keys(PROGRESS) as ProgressLabel[]).map((key) => ({
                      value: key,
                      label: `${PROGRESS[key].label} ${counts[key] ?? 0}`,
                    })),
                  ]}
                />
              </div>
              <div className="max-h-[560px] overflow-auto">
                <table className="w-full min-w-[720px] text-left">
                  <thead className="sticky top-0 bg-surface text-[12px] text-faint">
                    <tr className="border-b border-line">
                      <th className="px-4 py-2 font-normal">Place</th>
                      <th className="px-2 py-2 text-right font-normal">{programme.rows[0]?.baseline_period}</th>
                      <th className="px-2 py-2 text-right font-normal">{programme.rows[0]?.current_period}</th>
                      <th className="px-2 py-2 text-right font-normal">Change</th>
                      <th className="px-2 py-2 text-right font-normal">Residents reporting</th>
                      <th className="px-4 py-2 font-normal">What it means</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.region_id} className="border-b border-line last:border-0 hover:bg-subtle">
                        <td className="px-4 py-2">
                          {r.priority_id ? (
                            <Link to={`/priorities/${r.priority_id}`} className="font-medium hover:text-accent">{r.region_name}</Link>
                          ) : (
                            <span className="font-medium">{r.region_name}</span>
                          )}
                          <span className="ml-1.5 text-[12px] text-faint">{[r.level_name, r.parent_name].filter(Boolean).join(' · ')}</span>
                        </td>
                        <td className="px-2 py-2 text-right text-muted">
                          <Figure source={{ ...source, period: r.baseline_period }}>{formatNumber(r.baseline, 1)}%</Figure>
                        </td>
                        <td className="px-2 py-2 text-right">
                          <Figure source={{ ...source, period: r.current_period }}>{formatNumber(r.current, 1)}%</Figure>
                        </td>
                        <td className="num px-2 py-2 text-right">
                          {r.change > 0 ? '+' : ''}{formatNumber(r.change, 1)} pts
                        </td>
                        <td className="num px-2 py-2 text-right">
                          {r.residents_reporting === null ? <span className="text-faint">—</span> : formatNumber(r.residents_reporting)}
                        </td>
                        <td className="px-4 py-2">
                          <span title={PROGRESS[r.label].explain} className={cx('inline-flex whitespace-nowrap rounded px-1.5 py-0.5 text-[12px] font-medium', PROGRESS[r.label].className)}>
                            {PROGRESS[r.label].label}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="border-t border-line px-4 py-2.5 text-[12px] text-faint">
                "—" means fewer than the privacy floor of residents reported here, or none did. Places with a shown priority link to its evidence.
              </p>
            </Panel>
          )
        })
      )}

      <Panel title="Before and after completed projects">
        {projects.isPending ? (
          <Skeleton className="h-24" />
        ) : projects.isError ? (
          <ErrorState error={projects.error} />
        ) : !projects.data.has_project_data ? (
          <EmptyState title="No project data is loaded yet">
            When a country pack includes completed projects with completion dates, this compares complaints in the{' '}
            {projects.data.window_days} days before completion with the {projects.data.window_days} days after (skipping{' '}
            {projects.data.grace_days} days while the work settles in). Nothing here is estimated.
          </EmptyState>
        ) : projects.data.projects.length === 0 ? (
          <p className="text-muted">No project has been completed yet.</p>
        ) : (
          <table className="w-full text-left">
            <thead className="text-[12px] text-faint">
              <tr className="border-b border-line">
                <th className="py-2 pr-2 font-normal">Project</th>
                <th className="px-2 py-2 font-normal">Completed</th>
                <th className="px-2 py-2 text-right font-normal">Residents before</th>
                <th className="px-2 py-2 text-right font-normal">After</th>
                <th className="py-2 pl-2 font-normal">Result</th>
              </tr>
            </thead>
            <tbody>
              {projects.data.projects.map((p) => (
                <tr key={p.project_id} className="border-b border-line last:border-0">
                  <td className="py-2 pr-2">
                    <div className="font-medium">{p.title}</div>
                    <div className="text-[12px] text-faint">
                      {p.region_name} · {p.sector_label}
                      {p.amount !== null && p.currency && <> · <Figure source={{ name: p.source_name, url: p.source_url }}>{formatMoney(p.amount, p.currency, p.currency === 'INR' ? '₹' : '')}</Figure></>}
                    </div>
                  </td>
                  <td className="px-2 py-2 text-muted">{formatDate(p.completion_date)}</td>
                  <td className="num px-2 py-2 text-right">{p.reporters_before ?? '—'}</td>
                  <td className="num px-2 py-2 text-right">{p.reporters_after ?? '—'}</td>
                  <td className="py-2 pl-2">{PROJECT_LABELS[p.label]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  )
}

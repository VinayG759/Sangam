import { useState } from 'react'
import { useNavigate } from 'react-router'
import { formatDate, formatMoney, formatNumber, languageName } from '@/lib/format'
import { useRegionParam, withRegion } from '@/lib/regions'
import { ACTION_GROUPS, VERDICT_ORDER, VERDICTS } from '@/lib/verdicts'
import { BarList, ChartPanel, DataTable, Dumbbell, StackedBars, TimelineChart } from '@/ui/charts'
import { DemoTag } from '@/ui/DemoTag'
import { PageHeader, Stat } from '@/ui/primitives'
import { RegionPicker } from '@/ui/RegionPicker'
import { EmptyState, ErrorState, Skeleton } from '@/ui/states'
import { useOverview, useRollup } from '@/features/overview/api'
import { useAnalytics, useImpactProjects } from './api'

const STATUS_NAMES: Record<string, string> = {
  planned: 'Planned', sanctioned: 'Sanctioned', in_progress: 'In progress', stalled: 'Stalled', completed: 'Completed',
}
const OUTCOMES: [string, string][] = [
  ['IMPROVED', 'Complaints fell'], ['NO_CHANGE', 'No clear change'], ['WORSENED', 'Complaints rose'],
  ['TOO_EARLY', 'Too early to tell'], ['INSUFFICIENT_DATA', 'Too few reports'],
]
const shortDate = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

export default function AnalyticsPage() {
  const [region, setRegion] = useRegionParam()
  const navigate = useNavigate()
  const analytics = useAnalytics(region)
  const overview = useOverview(region)
  const rollup = useRollup(region)
  const impact = useImpactProjects()
  const [need, setNeed] = useState('')
  const [allPlaces, setAllPlaces] = useState(false)

  if (analytics.isPending) return <AnalyticsSkeleton />
  if (analytics.isError) return <ErrorState error={analytics.error} />
  const a = analytics.data
  const money = (v: number) => formatMoney(v, a.currency, a.currency_symbol)
  const progress = a.progress.find((p) => p.sector === need) ?? a.progress[0]
  const firstActive = a.timeline.findIndex((t) => t.reports > 0)
  const weeks = firstActive > 0 ? a.timeline.slice(firstActive) : a.timeline  // skip weeks before any report
  const PROGRESS_ROWS = 12
  const verdicts = overview.data?.verdicts ?? {}
  const goPriorities = (query: string) => navigate(withRegion(`/priorities${query}`, region))
  const groupOf = (v: string) => ACTION_GROUPS.find((g) => g.key !== 'all' && g.verdicts.includes(v as never))?.key ?? 'all'

  return (
    <div className={analytics.isPlaceholderData ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
      <PageHeader
        title={a.region ? `Analytics · ${a.region.name}` : 'Analytics'}
        description="The numbers behind the priorities, as charts. Every chart can be switched to a table, and every verdict comes from the same arithmetic as the Priorities list."
        actions={<RegionPicker value={region} onChange={setRegion} />}
      />

      {!a.run ? (
        <EmptyState title="No analysis has run yet" />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Citizen reports" value={formatNumber(a.totals.reports)} hint="All channels and languages" />
            <Stat label="Distinct residents" value={formatNumber(a.totals.residents)} hint="People, not messages" />
            <Stat label="Places needing action" value={formatNumber(a.totals.places_needing_action)} hint="A fund or audit verdict" to={withRegion('/priorities', region)} />
            <Stat
              label="Money stalled or not started"
              value={money(a.totals.money_flagged)}
              hint={<>Where residents still report the problem{a.totals.money_flagged_synthetic && <DemoTag />}</>}
              to={withRegion('/priorities?group=audit', region)}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <ChartPanel
              title="Reports per week"
              subtitle={`The last ${weeks.length} complete weeks`}
              table={<DataTable head={['Week of', 'Reports']} rows={weeks.map((t) => [formatDate(t.week), formatNumber(t.reports)])} />}
            >
              <TimelineChart points={weeks.map((t) => ({ label: t.week, value: t.reports }))} format={shortDate} />
            </ChartPanel>

            <ChartPanel
              title="Verdicts"
              subtitle="Places and needs with enough residents reporting. Click a bar to see them."
              table={<DataTable head={['Verdict', 'Action', 'Places']} rows={VERDICT_ORDER.map((v) => [VERDICTS[v].label, VERDICTS[v].action, formatNumber(verdicts[v] ?? 0)])} />}
            >
              <BarList
                labelWidth="10rem"
                rows={VERDICT_ORDER.map((v) => ({
                  key: v, label: VERDICTS[v].label, value: verdicts[v] ?? 0, color: VERDICTS[v].viz,
                  display: `${formatNumber(verdicts[v] ?? 0)}`,
                  onClick: () => goPriorities(`?group=${groupOf(v)}`),
                }))}
              />
            </ChartPanel>
          </div>

          <ChartPanel
            title="Verdicts by need"
            subtitle="Which services residents are asking about, and what the evidence says to do. Click a need to see its priorities."
            table={<DataTable
              head={['Need', ...VERDICT_ORDER.map((v) => VERDICTS[v].label)]}
              rows={a.needs.map((n) => [n.label, ...VERDICT_ORDER.map((v) => formatNumber(n.verdicts[v] ?? 0))])}
            />}
          >
            <StackedBars
              rows={a.needs.map((n) => ({ key: n.sector, label: n.label, values: n.verdicts as Record<string, number> }))}
              segments={VERDICT_ORDER.map((v) => ({ key: v, label: VERDICTS[v].label, color: VERDICTS[v].viz }))}
              onRow={(sector) => goPriorities(`?need=${sector}`)}
            />
          </ChartPanel>

          <div className="grid gap-6 lg:grid-cols-2">
            {progress && (
              <ChartPanel
                title={<>Official progress{progress.synthetic && <DemoTag />}</>}
                subtitle={<>{progress.statistic}, {progress.baseline_period} → {progress.current_period}, furthest behind first. Each {rollup.data?.level_name ?? 'place'} is the average of its blocks. Source: {progress.source_name}</>}
                actions={
                  <select
                    aria-label="Need"
                    value={progress.sector}
                    onChange={(e) => setNeed(e.target.value)}
                    className="h-7 max-w-40 rounded-md border border-line bg-surface px-2 text-[12px]"
                  >
                    {a.progress.map((p) => <option key={p.sector} value={p.sector}>{p.label}</option>)}
                  </select>
                }
                table={<DataTable
                  head={['Place', progress.baseline_period, progress.current_period, 'Change']}
                  rows={progress.rows.map((r) => [r.name, `${r.baseline}%`, `${r.current}%`, `${r.current - r.baseline > 0 ? '+' : ''}${(r.current - r.baseline).toFixed(1)}`])}
                />}
              >
                <Dumbbell
                  rows={progress.rows.slice(0, allPlaces ? undefined : PROGRESS_ROWS)
                    .map((r) => ({ key: r.id, label: r.name, before: r.baseline, after: r.current, onClick: () => setRegion(r.id) }))}
                  threshold={progress.served_threshold}
                  baselineLabel={progress.baseline_period ?? 'Before'}
                  currentLabel={progress.current_period ?? 'Now'}
                />
                {progress.rows.length > PROGRESS_ROWS && (
                  <button type="button" onClick={() => setAllPlaces((v) => !v)} className="mt-3 text-[12px] text-accent">
                    {allPlaces ? `Show the ${PROGRESS_ROWS} furthest behind` : `Show all ${progress.rows.length}`}
                  </button>
                )}
              </ChartPanel>
            )}

            <ChartPanel
              title={`Where action is needed${rollup.data?.level_name ? `, by ${rollup.data.level_name}` : ''}`}
              subtitle="Places inside each with a fund or audit verdict. Click to zoom in."
              table={<DataTable head={['Place', 'Needing action']} rows={(rollup.data?.items ?? []).map((i) => [i.name, formatNumber(i.places_needing_action)])} />}
            >
              {rollup.isPending ? <Skeleton className="h-64" /> : (
                <BarList
                  rows={(rollup.data?.items ?? []).slice(0, 12).map((i) => ({
                    key: i.id, label: i.name, value: i.places_needing_action,
                    onClick: () => (i.has_children ? setRegion(i.id) : goPriorities(`?region=${i.id}`)),
                  }))}
                />
              )}
            </ChartPanel>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <ChartPanel
              title={<>Public money by status{a.money.some((m) => m.synthetic) && <DemoTag />}</>}
              subtitle="Committed amounts in recorded projects"
              table={<DataTable head={['Status', 'Projects', 'Amount']} rows={a.money.map((m) => [STATUS_NAMES[m.status] ?? m.status, formatNumber(m.projects), money(m.amount)])} />}
            >
              <BarList
                labelWidth="6.5rem"
                format={money}
                rows={a.money.map((m) => ({ key: m.status, label: STATUS_NAMES[m.status] ?? m.status, value: m.amount }))}
              />
            </ChartPanel>

            <ChartPanel
              title="Did completed projects work?"
              subtitle="Distinct residents complaining before vs after each completed project (whole country)"
              table={<DataTable head={['Outcome', 'Projects']} rows={OUTCOMES.map(([k, l]) => [l, formatNumber((impact.data?.projects ?? []).filter((p) => p.label === k).length)])} />}
            >
              <BarList
                labelWidth="8rem"
                rows={OUTCOMES.map(([k, l]) => ({ key: k, label: l, value: (impact.data?.projects ?? []).filter((p) => p.label === k).length, onClick: () => navigate('/impact') }))}
              />
            </ChartPanel>

            <ChartPanel
              title="Languages received"
              subtitle="Reports are understood in the language they arrive in"
              table={<DataTable head={['Language', 'Reports']} rows={(overview.data?.languages ?? []).map((l) => [languageName(l.code), formatNumber(l.count)])} />}
            >
              <BarList labelWidth="5.5rem" rows={(overview.data?.languages ?? []).map((l) => ({ key: l.code, label: languageName(l.code), value: l.count }))} />
            </ChartPanel>
          </div>
        </div>
      )}
    </div>
  )
}

function AnalyticsSkeleton() {
  return (
    <>
      <Skeleton className="mb-6 h-10 w-72" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div>
    </>
  )
}

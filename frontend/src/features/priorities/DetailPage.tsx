import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, Download, ShieldCheck, TrendingUp } from 'lucide-react'
import { apiUrl } from '@/lib/api'
import { formatDate, formatMoney, formatNumber, languageName } from '@/lib/format'
import { usePack } from '@/lib/pack'
import { DemoTag } from '@/ui/DemoTag'
import { VERDICTS } from '@/lib/verdicts'
import { Figure } from '@/ui/Figure'
import { Button, ButtonLink, Panel, Tag } from '@/ui/primitives'
import { ErrorState, Skeleton } from '@/ui/states'
import { VerdictBadge } from '@/ui/VerdictBadge'
import { type Component, usePriority, useSourceReports } from './api'

const TERM_LABELS: Record<string, { name: string; explain: string }> = {
  demand: { name: 'Demand', explain: 'Residents reporting per head, relative to the busiest place' },
  deficit: { name: 'Deficit', explain: 'How far behind the best-served place the official statistic is' },
  reach: { name: 'Reach', explain: 'How many people live here (log scale)' },
  coverage: { name: 'Money already delivered', explain: 'Completed projects here; subtracts from the score' },
}

export default function PriorityDetailPage() {
  const { id = '' } = useParams()
  const pack = usePack()
  const query = usePriority(id)
  const sources = useSourceReports(id)
  const [showAll, setShowAll] = useState(false)

  if (query.isPending) return <Skeleton className="h-96" />
  if (query.isError) return <ErrorState error={query.error} title="Could not load this priority" />
  const p = query.data
  const meta = VERDICTS[p.verdict]
  const currency = pack.data?.currency ?? ''
  const symbol = pack.data?.currency_symbol ?? ''

  return (
    <>
      <Link to="/priorities" className="mb-4 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-3.5" /> Priorities
      </Link>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <VerdictBadge verdict={p.verdict} withAction />
            <Tag>Rank {p.rank}</Tag>
            {p.is_emerging && (
              <Tag className="text-delivery"><TrendingUp className="mr-1 size-3" /> Emerging</Tag>
            )}
          </div>
          <h1 className="mt-2 text-xl font-semibold tracking-tight">
            {p.region.name} · {p.sector_label}
          </h1>
          <p className="mt-0.5 text-muted">
            {[p.region.level_name, p.region.parent_name && `in ${p.region.parent_name}`].filter(Boolean).join(' ')}
            {' · '}reports from {formatDate(p.first_seen)} to {formatDate(p.last_seen)}
          </p>
        </div>
        {pack.data?.features.export && (
          <ButtonLink href={apiUrl(`/api/v1/priorities/${p.id}/brief.pdf`)} variant="primary">
            <Download className="size-4" /> Download brief (PDF)
          </ButtonLink>
        )}
      </header>

      <Panel className="mb-6">
        <p className="text-[15px] leading-relaxed">{p.summary}</p>
        <p className="mt-3 flex items-center gap-1.5 text-[12px] text-faint">
          <ShieldCheck className="size-3.5" />
          {p.summary_source === 'model'
            ? 'Written by AI. Every number was checked by code against the evidence below before it was accepted.'
            : 'Generated from a fixed template using only the evidence below.'}
        </p>
        <p className="mt-1 text-[12px] text-faint">{meta.meaning}</p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Evidence" className="lg:col-span-2" flush>
          <table className="w-full text-left">
            <tbody>
              {p.evidence.map((fact) => (
                <tr key={fact.id} className="border-b border-line align-top last:border-0">
                  <td className="w-10 px-4 py-2.5 text-[12px] text-faint">{fact.id}</td>
                  <td className="px-2 py-2.5">
                    {fact.label}
                    {fact.synthetic && <DemoTag />}
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <Figure source={{ name: fact.source_name, url: fact.source_url, period: fact.period }}>
                      {fact.unit === currency ? formatMoney(fact.value, currency, symbol) : formatNumber(fact.value, 2)}
                      {fact.unit === 'percent' ? '%' : ''}
                    </Figure>
                    {fact.unit && !['percent', currency].includes(fact.unit) && (
                      <div className="text-[11px] text-faint">{fact.unit}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <div className="space-y-6">
          <Panel title="How the score was computed">
            <ScoreBreakdown components={p.components} score={p.score} />
          </Panel>
          {p.estimated_cost !== null && (
            <Panel title="If funded">
              <div className="num text-lg font-semibold">{formatMoney(p.estimated_cost, currency, symbol)}</div>
              <p className="text-muted">to reach about {formatNumber(p.beneficiaries)} unserved {pack.data?.population_label}.</p>
              <p className="mt-2 text-[12px] text-faint">Planning estimate, not a sanctioned amount. See F8 for the assumption.</p>
            </Panel>
          )}
        </div>
      </div>

      <Panel
        title={`What residents said (${formatNumber(p.distinct_reporters)} people, ${formatNumber(p.report_count)} reports)`}
        className="mt-6"
        flush
      >
        {sources.isPending ? (
          <div className="space-y-2 p-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : sources.isError ? (
          <div className="p-4"><ErrorState error={sources.error} /></div>
        ) : (
          <ul>
            {sources.data.slice(0, showAll ? undefined : 6).map((r, i) => (
              <li key={i} className="border-b border-line px-4 py-3 last:border-0">
                <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[12px] text-faint">
                  <span>{formatDate(r.created_at)}</span>
                  <Tag>{languageName(r.language)}</Tag>
                  <Tag>{r.channel}</Tag>
                  {r.is_synthetic && <Tag>synthetic</Tag>}
                </div>
                {r.language !== 'en' && r.text_original && <p lang={r.language ?? undefined}>{r.text_original}</p>}
                <p className={r.language !== 'en' ? 'text-muted' : ''}>{r.text_en}</p>
              </li>
            ))}
          </ul>
        )}
        {sources.data && sources.data.length > 6 && !showAll && (
          <div className="border-t border-line px-4 py-2.5">
            <Button onClick={() => setShowAll(true)}>Show all {sources.data.length} recent reports</Button>
          </div>
        )}
        <p className="border-t border-line px-4 py-2.5 text-[12px] text-faint">
          Personal details are removed before anything is stored. Who reported is never shown or stored.
        </p>
      </Panel>
    </>
  )
}

function ScoreBreakdown({ components, score }: { components: Record<string, Component> & { missing?: string[] }; score: number }) {
  const terms = Object.entries(components).filter(([key]) => key !== 'missing') as [string, Component][]
  const missing = components.missing ?? []
  return (
    <div>
      <ul className="space-y-3">
        {terms.map(([key, c]) => (
          <li key={key}>
            <div className="flex items-baseline justify-between text-[13px]">
              <span title={TERM_LABELS[key]?.explain}>{TERM_LABELS[key]?.name ?? key}</span>
              <span className={`num ${c.contribution < 0 ? 'text-unserved' : ''}`}>
                {c.contribution >= 0 ? '+' : ''}{formatNumber(c.contribution, 1)}
              </span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-subtle">
              <div
                className={`h-1.5 rounded-full ${c.contribution < 0 ? 'bg-unserved' : 'bg-accent'}`}
                style={{ width: `${Math.min(100, Math.abs(c.value) * 100)}%` }}
              />
            </div>
            <div className="mt-0.5 text-[11px] text-faint">
              value {formatNumber(c.value, 2)} × weight {formatNumber(c.weight, 2)}
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-baseline justify-between border-t border-line pt-3 font-medium">
        <span>Score</span>
        <span className="num">{formatNumber(score, 1)} / 100</span>
      </div>
      <p className="mt-2 text-[12px] text-faint">
        Points = value × weight, scaled so the weights of the terms with data add up to 100.
      </p>
      {missing.length > 0 && (
        <p className="mt-2 text-[12px] text-faint">
          No data for {missing.join(', ')}; the remaining weights were re-balanced. Weights are set by the government in
          the country pack, not by Sangam.
        </p>
      )}
    </div>
  )
}

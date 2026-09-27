import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { get } from '@/lib/api'
import { formatDate, formatNumber, languageName } from '@/lib/format'
import { needLabel, usePack } from '@/lib/pack'
import { Button, inputStyle, PageHeader, Tag } from '@/ui/primitives'
import { EmptyState, ErrorState, Skeleton } from '@/ui/states'

interface ReportItem {
  created_at: string
  channel: string
  language: string | null
  sector: string
  region_name: string
  text_en: string | null
  text_original: string | null
  urgency: number | null
  is_synthetic: boolean
}

export default function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const pack = usePack()
  const sector = params.get('need') ?? ''
  const language = params.get('language') ?? ''
  const page = Number(params.get('page') ?? '1')

  const query = useQuery({
    queryKey: ['reports', sector, language, page],
    queryFn: () => {
      const q = new URLSearchParams({ page: String(page) })
      if (sector) q.set('sector', sector)
      if (language) q.set('language', language)
      return get<{ total: number; page_size: number; items: ReportItem[] }>(`/api/v1/reports?${q}`)
    },
    placeholderData: keepPreviousData,
  })

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }

  const pages = query.data ? Math.max(1, Math.ceil(query.data.total / query.data.page_size)) : 1

  return (
    <>
      <PageHeader
        title="Citizen reports"
        description="What residents said, in their own words and in English. Personal details are removed before storage, and only places with enough reporters to protect anonymity are shown."
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <select aria-label="Need" className={inputStyle} value={sector} onChange={(e) => update('need', e.target.value)}>
          <option value="">All needs</option>
          {pack.data?.needs.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
        </select>
        <select aria-label="Language" className={inputStyle} value={language} onChange={(e) => update('language', e.target.value)}>
          <option value="">All languages</option>
          {pack.data?.languages.map((code) => <option key={code} value={code}>{languageName(code)}</option>)}
        </select>
      </div>

      {query.isPending ? (
        <div className="space-y-2">{[...Array(8)].map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="No reports to show" />
      ) : (
        <>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {query.data.items.map((r, i) => (
              <li key={i} className="grid gap-1 px-4 py-3 md:grid-cols-[11rem_1fr]">
                <div className="text-[12px] text-muted">
                  <div className="font-medium text-ink">{r.region_name}</div>
                  <div>{needLabel(pack.data, r.sector)}</div>
                  <div className="text-faint">{formatDate(r.created_at)}</div>
                </div>
                <div>
                  {r.language !== 'en' && r.text_original && <p lang={r.language ?? undefined}>{r.text_original}</p>}
                  <p className={r.language !== 'en' ? 'text-muted' : ''}>{r.text_en}</p>
                  <div className="mt-1 flex gap-1.5">
                    <Tag>{languageName(r.language)}</Tag>
                    <Tag>{r.channel}</Tag>
                    {r.is_synthetic && <Tag>synthetic</Tag>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-between text-[13px] text-muted">
            <span className="num">{formatNumber(query.data.total)} reports · page {page} of {pages}</span>
            <div className="flex gap-2">
              <Button disabled={page <= 1} onClick={() => update('page', String(page - 1))}>Previous</Button>
              <Button disabled={page >= pages} onClick={() => update('page', String(page + 1))}>Next</Button>
            </div>
          </div>
        </>
      )}
    </>
  )
}

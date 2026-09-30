import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { get, type Verdict } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { needLabel, usePack } from '@/lib/pack'
import { VERDICTS } from '@/lib/verdicts'
import { cx } from '@/lib/cx'
import { Button, inputStyle } from '@/ui/primitives'
import { ErrorState, Skeleton } from '@/ui/states'
import { LANGUAGES, useLanguage } from './i18n'
import { Shell } from './ReportPage'

interface Track {
  tracking_id: string
  received_at: string
  stage: 'received' | 'understood' | 'located' | 'prioritised' | 'unlocated'
  sector: string | null
  region_name: string | null
  verdict: Verdict | null
  rank: number | null
  language: string | null
  text_original: string | null
  text_en: string | null
}

const STEPS = ['received', 'understood', 'located', 'prioritised'] as const

export default function TrackPage() {
  const { trackingId } = useParams()
  const navigate = useNavigate()
  const [input, setInput] = useState(trackingId ?? '')
  const [showText, setShowText] = useState(false)
  const pack = usePack()
  const [lang, setLang, t] = useLanguage()
  const steps = [
    { key: 'received', label: t.stReceived, hint: null },
    { key: 'understood', label: t.stUnderstood, hint: t.stUnderstoodHint },
    { key: 'located', label: t.stLocated, hint: t.stLocatedHint },
    { key: 'prioritised', label: t.stPrioritised, hint: t.stPrioritisedHint },
  ]
  const query = useQuery({
    queryKey: ['track', trackingId],
    queryFn: () => get<Track>(`/api/v1/track/${encodeURIComponent(trackingId!)}`),
    enabled: Boolean(trackingId),
    retry: false,
  })

  const reached = query.data ? STEPS.findIndex((s) => s === query.data.stage) : -1

  return (
    <Shell lang={lang} onLang={setLang} t={t}>
      <h1 className="text-xl font-semibold tracking-tight">{t.trackTitle}</h1>
      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (input.trim()) navigate(`/track/${input.trim().toUpperCase()}`)
        }}
      >
        <input dir="ltr" aria-label={t.trackTitle} className={`${inputStyle} num min-w-0 flex-1 uppercase`} placeholder="SG-XXXXXX" value={input} onChange={(e) => setInput(e.target.value)} />
        <Button variant="primary" type="submit">{t.check}</Button>
      </form>

      <div className="mt-6">
        {query.isFetching && <Skeleton className="h-48" />}
        {query.isError && <ErrorState error={query.error} title={t.notFound} />}
        {query.data && !query.isFetching && (
          <div className="rounded-lg border border-line bg-surface p-5">
            <div className="num text-lg font-semibold">{query.data.tracking_id}</div>
            <p className="text-muted">
              {[query.data.sector && needLabel(pack.data, query.data.sector), query.data.region_name].filter(Boolean).join(' · ')}
              {' · '}{t.receivedOn} {formatDate(query.data.received_at)}
            </p>
            {query.data.stage === 'unlocated' ? (
              <p className="mt-4 text-muted">{t.unlocated}</p>
            ) : (
              <ol className="mt-5 space-y-4">
                {steps.map((step, i) => (
                  <li key={step.key} className="flex gap-3">
                    <span
                      className={cx(
                        'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border',
                        i <= reached ? 'border-accent bg-accent text-white' : 'border-line text-faint',
                      )}
                    >
                      {i <= reached && <Check className="size-3" strokeWidth={3} />}
                    </span>
                    <div>
                      <div className={i <= reached ? 'font-medium' : 'text-muted'}>{step.label}</div>
                      {step.hint && <div className="text-[12px] text-faint">{step.hint}</div>}
                      {step.key === 'prioritised' && query.data.verdict && (
                        <div className="mt-1 text-[13px]">
                          {VERDICTS[query.data.verdict].label} · {t.rank} {query.data.rank}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {(query.data.text_original || query.data.text_en) && (
              <div className="mt-5 border-t border-line pt-4">
                <Button onClick={() => setShowText((v) => !v)} aria-expanded={showText}>
                  {showText ? t.hideReport : t.showReport}
                </Button>
                {showText && (
                  <dl className="mt-4 space-y-3">
                    {query.data.text_original && (
                      <div>
                        <dt className="text-[12px] text-faint">
                          {t.youSaid}
                          {query.data.language && ` · ${LANGUAGES.find((l) => l.code === query.data.language)?.name ?? query.data.language}`}
                        </dt>
                        <dd className="mt-0.5 whitespace-pre-line" dir="auto">{query.data.text_original}</dd>
                      </div>
                    )}
                    {query.data.text_en && query.data.language !== 'en' && (
                      <div>
                        <dt className="text-[12px] text-faint">{t.inEnglish}</dt>
                        <dd className="mt-0.5 whitespace-pre-line text-muted" dir="ltr">{query.data.text_en}</dd>
                      </div>
                    )}
                  </dl>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      <p className="mt-6 text-center text-[12px]">
        <Link to="/report" className="text-accent">{t.reportNew}</Link>
      </p>
    </Shell>
  )
}

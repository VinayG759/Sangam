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
import { Shell } from './ReportPage'

interface Track {
  tracking_id: string
  received_at: string
  stage: 'received' | 'understood' | 'located' | 'prioritised' | 'unlocated'
  sector: string | null
  region_name: string | null
  verdict: Verdict | null
  rank: number | null
}

const STEPS = [
  { key: 'received', label: 'Received' },
  { key: 'understood', label: 'Understood', hint: 'Language, need and urgency recognised' },
  { key: 'located', label: 'Placed on the map', hint: 'Grouped with others reporting the same need nearby' },
  { key: 'prioritised', label: 'In the priority list', hint: 'Enough residents reported for officials to see it' },
] as const

export default function TrackPage() {
  const { trackingId } = useParams()
  const navigate = useNavigate()
  const [input, setInput] = useState(trackingId ?? '')
  const pack = usePack()
  const query = useQuery({
    queryKey: ['track', trackingId],
    queryFn: () => get<Track>(`/api/v1/track/${encodeURIComponent(trackingId!)}`),
    enabled: Boolean(trackingId),
    retry: false,
  })

  const reached = query.data ? STEPS.findIndex((s) => s.key === query.data.stage) : -1

  return (
    <Shell>
      <h1 className="text-xl font-semibold tracking-tight">Track a report</h1>
      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (input.trim()) navigate(`/track/${input.trim().toUpperCase()}`)
        }}
      >
        <input className={`${inputStyle} num flex-1 uppercase`} placeholder="SG-XXXXXX" value={input} onChange={(e) => setInput(e.target.value)} />
        <Button variant="primary" type="submit">Check</Button>
      </form>

      <div className="mt-6">
        {query.isFetching && <Skeleton className="h-48" />}
        {query.isError && <ErrorState error={query.error} title="Report not found" />}
        {query.data && !query.isFetching && (
          <div className="rounded-lg border border-line bg-surface p-5">
            <div className="num text-lg font-semibold">{query.data.tracking_id}</div>
            <p className="text-muted">
              {[query.data.sector && needLabel(pack.data, query.data.sector), query.data.region_name].filter(Boolean).join(' · ')}
              {' · '}received {formatDate(query.data.received_at)}
            </p>
            {query.data.stage === 'unlocated' ? (
              <p className="mt-4 text-muted">
                We could not work out the place for this report. It is saved and counted, but cannot be shown on the map.
              </p>
            ) : (
              <ol className="mt-5 space-y-4">
                {STEPS.map((step, i) => (
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
                      {'hint' in step && <div className="text-[12px] text-faint">{step.hint}</div>}
                      {step.key === 'prioritised' && query.data.verdict && (
                        <div className="mt-1 text-[13px]">
                          {VERDICTS[query.data.verdict].label} · rank {query.data.rank}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </div>
      <p className="mt-6 text-center text-[12px]">
        <Link to="/report" className="text-accent">Report a new problem</Link>
      </p>
    </Shell>
  )
}

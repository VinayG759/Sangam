import { useState, useEffect } from 'react'
import { api, type Report, type PackInfo } from '@/api'

interface ReportsTableProps {
  pack: PackInfo | null;
}

const URGENCY_COLOR = (u: number) => {
  if (u >= 4.5) return 'var(--verdict-unserved)';
  if (u >= 3.5) return 'var(--verdict-stalled)';
  if (u >= 2.5) return 'var(--verdict-underfunded)';
  return 'var(--verdict-wellserved)';
}

const SENTIMENT_EMOJI: Record<string, string> = {
  negative: '😟', neutral: '😐', positive: '😊',
}

const PAGE_SIZE = 20

export default function ReportsTable({ pack }: ReportsTableProps) {
  const [reports, setReports]   = useState<Report[]>([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(0)
  const [sector, setSector]     = useState('')
  const [loading, setLoading]   = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)

  useEffect(() => {
    setLoading(true)
    api.reports({ sector: sector || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then(r => { setReports(r.reports); setTotal(r.total) })
      .finally(() => setLoading(false))
  }, [sector, page])

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const sectors = pack?.sectors ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Filter bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <select
          className="select"
          value={sector}
          onChange={e => { setSector(e.target.value); setPage(0) }}
          style={{ minWidth: 160 }}
        >
          <option value="">All Sectors</option>
          {sectors.map(s => (
            <option key={s.key} value={s.key}>{s.name}</option>
          ))}
        </select>

        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {total.toLocaleString('en-IN')} reports
        </span>
      </div>

      {/* Table */}
      <div className="card" style={{ overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[...Array(5)].map((_, i) => <div key={i} className="skeleton" style={{ height: 56 }} />)}
          </div>
        ) : !reports.length ? (
          <div className="empty-state">
            <span style={{ fontSize: 32 }}>📭</span>
            <span>No reports found</span>
          </div>
        ) : (
          <div>
            {/* Header */}
            <div style={{
              display: 'grid', gridTemplateColumns: '2fr 90px 60px 80px 60px',
              padding: '10px 16px', borderBottom: '1px solid var(--border)',
              fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
            }}>
              <span>Report</span>
              <span>Sector</span>
              <span>Lang</span>
              <span>Urgency</span>
              <span>Mood</span>
            </div>

            {reports.map(r => (
              <div key={r.id}>
                <div
                  onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                  style={{
                    display: 'grid', gridTemplateColumns: '2fr 90px 60px 80px 60px',
                    padding: '12px 16px', cursor: 'pointer',
                    borderBottom: '1px solid var(--border)',
                    transition: 'background var(--transition)',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = '')}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.pii_redacted_text || r.english_translation || r.raw_text}
                    </div>
                    {r.specific_issue && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{r.specific_issue}</div>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', textTransform: 'capitalize', alignSelf: 'center' }}>
                    {r.sector}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', alignSelf: 'center', fontFamily: 'monospace' }}>
                    {r.detected_language}
                  </div>
                  <div style={{ alignSelf: 'center' }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                      background: `${URGENCY_COLOR(r.urgency_score)}20`,
                      color: URGENCY_COLOR(r.urgency_score),
                    }}>
                      {r.urgency_score.toFixed(1)}
                    </span>
                  </div>
                  <div style={{ fontSize: 18, alignSelf: 'center' }}>
                    {SENTIMENT_EMOJI[r.sentiment] ?? '😐'}
                  </div>
                </div>

                {/* Expanded detail */}
                {expanded === r.id && (
                  <div style={{
                    padding: '12px 16px 16px 24px',
                    borderBottom: '1px solid var(--border)',
                    background: 'var(--bg-input)',
                    display: 'flex', flexDirection: 'column', gap: 10,
                  }}>
                    {r.raw_text !== r.english_translation && (
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Original Text</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>{r.raw_text}</div>
                      </div>
                    )}
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>English Translation</div>
                      <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>{r.english_translation}</div>
                    </div>
                    {r.reported_at && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        Reported: {new Date(r.reported_at).toLocaleString('en-IN')}
                        {r.cluster_id ? ` · Cluster #${r.cluster_id}` : ''}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <button className="btn btn-ghost" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>
            ← Prev
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Page {page + 1} of {totalPages}
          </span>
          <button className="btn btn-ghost" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>
            Next →
          </button>
        </div>
      )}
    </div>
  )
}

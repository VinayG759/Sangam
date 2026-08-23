import { useState, useEffect } from 'react'
import { api, type PriorityDetail } from '@/api'
import type { Priority } from '@/api'

interface PriorityCardProps {
  priority: Priority;
}

export default function PriorityCard({ priority }: PriorityCardProps) {
  const [detail, setDetail] = useState<PriorityDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'brief' | 'evidence'>('brief')

  useEffect(() => {
    setLoading(true)
    setDetail(null)
    api.priorityDetail(priority.id)
      .then(setDetail)
      .finally(() => setLoading(false))
  }, [priority.id])

  const breakdown = (detail?.evidence_bundle ?? {}) as Record<string, unknown>

  const briefTabs = ['brief', 'evidence'] as const

  return (
    <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '20px 24px 16px',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
          Priority Detail
        </div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, marginBottom: 8 }}>
          {priority.title}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Score: <strong style={{ color: 'var(--text-primary)' }}>{priority.score.toFixed(1)}</strong>
          </span>
          <span style={{ color: 'var(--text-muted)' }}>·</span>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {priority.report_count} citizen reports
          </span>
          <span style={{ color: 'var(--text-muted)' }}>·</span>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {priority.region_name}
          </span>
          {Boolean(priority.details?.partial_evidence) && (
            <>
              <span style={{ color: 'var(--text-muted)' }}>·</span>
              <span style={{ fontSize: 11, color: '#f59e0b', fontWeight: 600, border: '1px solid #fcd34d', padding: '2px 4px', borderRadius: 4 }}>
                Partial Evidence
              </span>
            </>
          )}
        </div>
      </div>

      {/* Tab toggle */}
      <div style={{ padding: '12px 24px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 4 }}>
        {briefTabs.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600,
              border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)',
              background: activeTab === tab ? 'var(--accent-blue)' : 'var(--bg-input)',
              color: activeTab === tab ? '#fff' : 'var(--text-muted)',
              transition: 'all var(--transition)',
            }}
          >
            {tab === 'brief' ? '📄 Policy Brief' : '🔍 Evidence'}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[...Array(4)].map((_, i) => <div key={i} className="skeleton" style={{ height: 60, borderRadius: 8 }} />)}
          </div>
        ) : !detail ? (
          <div className="empty-state">No data available</div>
        ) : activeTab === 'brief' ? (
          <BriefPanel brief={detail.narrative_brief} />
        ) : (
          <EvidencePanel evidence={breakdown} />
        )}
      </div>
    </div>
  )
}

function BriefPanel({ brief }: { brief: PriorityDetail['narrative_brief'] }) {
  const sections = [
    { icon: '📋', title: 'Summary',          text: brief.summary },
    { icon: '⬆',  title: 'Why Prioritized',  text: brief.why_prioritized },
    { icon: '💰', title: 'Fiscal Gap',        text: brief.fiscal_gap_analysis },
    { icon: '✅', title: 'Recommended Action', text: brief.recommended_action },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {sections.map(s => (
        <div key={s.title} style={{
          background: 'var(--bg-input)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 16px',
          border: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
            {s.icon} {s.title}
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65 }}>
            {s.text}
          </div>
        </div>
      ))}
    </div>
  )
}

function EvidencePanel({ evidence }: { evidence: Record<string, unknown> }) {
  if (!Object.keys(evidence).length) {
    return <div className="empty-state">No evidence bundle attached</div>
  }

  const fmt = (v: unknown): string => {
    if (typeof v === 'number') {
      if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
      if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
      return typeof v === 'number' && v !== Math.floor(v) ? v.toFixed(2) : String(v);
    }
    if (typeof v === 'boolean') return v ? '✅ Yes' : '❌ No';
    if (v === null || v === undefined) return '—';
    if (Array.isArray(v)) return `[${v.length} items]`;
    if (typeof v === 'object') return '{...}';
    return String(v);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {Object.entries(evidence).map(([k, v]) => (
        <div key={k} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
          padding: '10px 14px',
          background: 'var(--bg-input)', borderRadius: 8,
          border: '1px solid var(--border)',
          gap: 12,
        }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'monospace', flexShrink: 0 }}>
            {k}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 600, textAlign: 'right' }}>
            {fmt(v)}
          </span>
        </div>
      ))}
    </div>
  )
}

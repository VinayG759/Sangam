import type { Priority } from '@/api'

interface PriorityListProps {
  priorities: Priority[];
  selectedId: number | null;
  onSelect: (p: Priority) => void;
  loading?: boolean;
}

const VERDICT_META: Record<string, { label: string; cls: string; color: string }> = {
  UNSERVED_GAP:       { label: 'Unserved Gap',       cls: 'badge-unserved',    color: 'var(--verdict-unserved)' },
  STALLED_ALLOCATION: { label: 'Stalled Allocation',  cls: 'badge-stalled',     color: 'var(--verdict-stalled)' },
  UNDERFUNDED_CRITICAL:{ label: 'Underfunded',        cls: 'badge-underfunded', color: 'var(--verdict-underfunded)' },
  WELL_SERVED:        { label: 'Well Served',         cls: 'badge-wellserved',  color: 'var(--verdict-wellserved)' },
}

const SECTOR_ICONS: Record<string, string> = {
  water: '💧', roads: '🛣️', sanitation: '♻️',
  health: '🏥', education: '🏫', electricity: '⚡', other: '📋',
}

function ScoreRing({ score, color }: { score: number; color: string }) {
  const radius = 22;
  const circ   = 2 * Math.PI * radius;
  const dash   = (score / 100) * circ;

  return (
    <div style={{ position: 'relative', width: 52, height: 52, flexShrink: 0 }}>
      <svg width="52" height="52" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="26" cy="26" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={4} />
        <circle
          cx="26" cy="26" r={radius} fill="none"
          stroke={color} strokeWidth={4}
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 600ms cubic-bezier(0.4,0,0.2,1)' }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)',
      }}>
        {Math.round(score)}
      </div>
    </div>
  )
}

export default function PriorityList({ priorities, selectedId, onSelect, loading }: PriorityListProps) {
  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[...Array(5)].map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 76, borderRadius: 'var(--radius-md)' }} />
        ))}
      </div>
    )
  }

  if (!priorities.length) {
    return (
      <div className="empty-state">
        <span style={{ fontSize: 32 }}>📋</span>
        <span>No priorities found</span>
        <span style={{ fontSize: 11 }}>Run /reprocess to generate priorities from citizen reports</span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {priorities.map((p, i) => {
        const meta = VERDICT_META[p.verdict] ?? VERDICT_META.WELL_SERVED;
        const isSelected = p.id === selectedId;

        return (
          <div
            key={p.id}
            onClick={() => onSelect(p)}
            className="card fade-up"
            style={{
              animationDelay: `${i * 40}ms`,
              cursor: 'pointer',
              padding: '14px 16px',
              display: 'flex', alignItems: 'center', gap: 14,
              borderColor: isSelected ? 'var(--border-focus)' : undefined,
              background: isSelected ? 'rgba(59, 110, 245, 0.08)' : undefined,
              transition: 'all var(--transition)',
            }}
          >
            <div style={{ fontSize: 22, lineHeight: 1, flexShrink: 0 }}>
              {SECTOR_ICONS[p.sector] ?? SECTOR_ICONS.other}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)', marginBottom: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {p.title}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span className={`badge ${meta.cls}`}>{meta.label}</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {p.region_name} · {p.report_count} reports
                </span>
              </div>
            </div>

            <ScoreRing score={p.score} color={meta.color} />
          </div>
        )
      })}
    </div>
  )
}

import { useEffect, useRef } from 'react'

interface MetricCardProps {
  label: string;
  value: number | string;
  sub?: string;
  icon: string;
  color?: string;
  format?: 'number' | 'currency' | 'raw';
  delay?: number;
}

function formatValue(value: number | string, format: 'number' | 'currency' | 'raw'): string {
  if (typeof value === 'string') return value;
  if (format === 'raw') return String(value);
  if (format === 'currency') {
    if (value >= 1e7) return `₹${(value / 1e7).toFixed(1)} Cr`;
    if (value >= 1e5) return `₹${(value / 1e5).toFixed(1)} L`;
    return `₹${value.toLocaleString('en-IN')}`;
  }
  // number
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000)     return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString('en-IN');
}

export default function MetricCard({ label, value, sub, icon, color = 'var(--accent-blue)', format = 'number', delay = 0 }: MetricCardProps) {
  const numRef = useRef<HTMLDivElement>(null);

  // Animate count-up for numeric values
  useEffect(() => {
    if (typeof value !== 'number' || !numRef.current) return;
    const el = numRef.current;
    const duration = 1000;
    const start = performance.now();
    const target = value;

    function tick(now: number) {
      const elapsed = now - start - delay;
      if (elapsed < 0) { requestAnimationFrame(tick); return; }
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
      const current = Math.round(eased * target);
      el.textContent = formatValue(current, format);
      if (progress < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }, [value, format, delay]);

  return (
    <div className="card card-pad fade-up" style={{
      animationDelay: `${delay}ms`,
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          {label}
        </span>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: `${color}20`,
          border: `1px solid ${color}30`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 18,
        }}>
          {icon}
        </div>
      </div>

      <div ref={numRef} style={{
        fontFamily: 'var(--font-display)',
        fontSize: 32,
        fontWeight: 700,
        color: 'var(--text-primary)',
        lineHeight: 1,
      }}>
        {formatValue(typeof value === 'number' ? 0 : value, format)}
      </div>

      {sub && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{sub}</div>
      )}

      {/* Accent bar */}
      <div style={{
        height: 2, borderRadius: 999,
        background: `linear-gradient(90deg, ${color}, transparent)`,
        marginTop: 4,
      }} />
    </div>
  )
}

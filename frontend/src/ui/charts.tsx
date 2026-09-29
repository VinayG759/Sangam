/*
 * Small, dependency-free charts. The rules they follow (see the dataviz guide):
 * thin marks with a 4px rounded data-end, a 2px surface gap between touching
 * fills, hairline recessive gridlines, text in text colours (never the series
 * colour), a legend for two or more series, a tooltip on hover and keyboard
 * focus, and a table view for every chart so no value is hidden behind hover.
 */
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { Table2, BarChart3 } from 'lucide-react'
import { cx } from '@/lib/cx'
import { xTicks } from '@/lib/ticks'
import { Panel } from './primitives'

// ── Shell: panel + chart/table switch ────────────────────────────────────────

export function ChartPanel({ title, subtitle, table, children, actions, className }: {
  title: ReactNode
  subtitle?: ReactNode
  table: ReactNode
  children: ReactNode
  actions?: ReactNode
  className?: string
}) {
  const [asTable, setAsTable] = useState(false)
  return (
    <Panel
      className={className}
      title={title}
      actions={
        <div className="flex items-center gap-2">
          {actions}
          <button
            type="button"
            onClick={() => setAsTable((v) => !v)}
            aria-pressed={asTable}
            title={asTable ? 'Show as chart' : 'Show as table'}
            className="inline-flex size-7 items-center justify-center rounded-md border border-line text-muted hover:bg-subtle hover:text-ink"
          >
            {asTable ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />}
            <span className="sr-only">{asTable ? 'Show as chart' : 'Show as table'}</span>
          </button>
        </div>
      }
    >
      {subtitle && <p className="-mt-1 mb-3 text-[12px] text-muted">{subtitle}</p>}
      {asTable ? <div className="overflow-x-auto">{table}</div> : children}
    </Panel>
  )
}

export function DataTable({ head, rows }: { head: ReactNode[]; rows: ReactNode[][] }) {
  return (
    <table className="w-full text-left text-[13px]">
      <thead className="text-[12px] text-faint">
        <tr className="border-b border-line">
          {head.map((h, i) => <th key={i} className={cx('py-1.5 pr-3 font-normal', i > 0 && 'text-right')}>{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-line last:border-0">
            {r.map((c, j) => <td key={j} className={cx('py-1.5 pr-3', j > 0 && 'num text-right')}>{c}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Legend({ items }: { items: { key: string; label: string; color: string }[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
      {items.map((i) => (
        <li key={i.key} className="inline-flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-sm" style={{ background: i.color }} />
          {i.label}
        </li>
      ))}
    </ul>
  )
}

// ── Tooltip (hover and keyboard focus show the same thing) ───────────────────

interface Tip { x: number; y: number; width: number; content: ReactNode }

function useTip() {
  const [tip, setTip] = useState<Tip | null>(null)
  // A callback ref kept in state, so rendering never reads a mutable ref.
  const [container, attach] = useState<HTMLDivElement | null>(null)
  const show = (e: { currentTarget: Element }, content: ReactNode) => {
    const box = container?.getBoundingClientRect()
    const r = e.currentTarget.getBoundingClientRect()
    if (!box) return
    setTip({ x: r.left - box.left + r.width / 2, y: r.top - box.top, width: box.width, content })
  }
  const node = tip && (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-20 w-max max-w-56 -translate-x-1/2 -translate-y-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12px] leading-snug text-ink shadow-sm"
      style={{ left: Math.max(60, Math.min(tip.x, tip.width - 60)), top: tip.y - 6 }}
    >
      {tip.content}
    </div>
  )
  return { attach, show, hide: () => setTip(null), node }
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

// ── Horizontal bars: magnitude by category ──────────────────────────────────

export interface BarRow {
  key: string
  label: ReactNode
  value: number
  display?: string
  color?: string
  onClick?: () => void
}

export function BarList({ rows, color = 'var(--viz-accent)', format = (v: number) => v.toLocaleString('en-IN'), labelWidth = '9rem' }: {
  rows: BarRow[]
  color?: string
  format?: (v: number) => string
  labelWidth?: string
}) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  const { attach, show, hide, node: tipNode } = useTip()
  if (!rows.length) return <p className="text-muted">No data yet.</p>
  return (
    <div ref={attach} className="relative">
      <ul className="space-y-1.5">
        {rows.map((row) => {
          const Tag = row.onClick ? 'button' : 'div'
          return (
            <li key={row.key}>
              <Tag
                type={row.onClick ? 'button' : undefined}
                onClick={row.onClick}
                tabIndex={0}
                onMouseEnter={(e) => show(e, <><span className="text-muted">{row.label}</span>: <b>{row.display ?? format(row.value)}</b></>)}
                onFocus={(e) => show(e, <><span className="text-muted">{row.label}</span>: <b>{row.display ?? format(row.value)}</b></>)}
                onMouseLeave={hide}
                onBlur={hide}
                className={cx('grid min-h-6 w-full items-center gap-2 rounded text-left text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
                  row.onClick && 'cursor-pointer hover:bg-subtle')}
                style={{ gridTemplateColumns: `minmax(0, ${labelWidth}) minmax(0, 1fr) auto` }}
              >
                <span className="truncate text-muted">{row.label}</span>
                <span className="h-2.5">
                  <span
                    className="block h-2.5 rounded-r"
                    style={{ width: `${Math.max(row.value ? 1.5 : 0, (row.value / max) * 100)}%`, background: row.color ?? color }}
                  />
                </span>
                <span className="num min-w-10 text-right text-[12px] text-ink">{row.display ?? format(row.value)}</span>
              </Tag>
            </li>
          )
        })}
      </ul>
      {tipNode}
    </div>
  )
}

// ── Stacked bars: part-to-whole per row ─────────────────────────────────────

export interface Segment { key: string; label: string; color: string }

export function StackedBars({ rows, segments, onRow }: {
  rows: { key: string; label: string; values: Record<string, number> }[]
  segments: Segment[]
  onRow?: (key: string) => void
}) {
  const { attach, show, hide, node: tipNode } = useTip()
  const max = Math.max(1, ...rows.map((r) => segments.reduce((s, g) => s + (r.values[g.key] ?? 0), 0)))
  return (
    <div ref={attach} className="relative">
      <Legend items={segments} />
      <ul className="space-y-2">
        {rows.map((row) => {
          const total = segments.reduce((s, g) => s + (row.values[g.key] ?? 0), 0)
          return (
            <li
              key={row.key}
              className={cx('grid items-center gap-2 text-[13px]', onRow && 'cursor-pointer')}
              style={{ gridTemplateColumns: 'minmax(0, 10rem) minmax(0, 1fr) auto' }}
              onClick={onRow ? () => onRow(row.key) : undefined}
            >
              <span className="truncate text-muted">{row.label}</span>
              <span className="flex h-3 gap-[2px]" style={{ width: `${(total / max) * 100}%` }}>
                {segments.filter((g) => row.values[g.key]).map((g, i, shown) => (
                  <span
                    key={g.key}
                    tabIndex={0}
                    onMouseEnter={(e) => show(e, <><b>{row.label}</b><br />{g.label}: <b>{row.values[g.key]}</b></>)}
                    onFocus={(e) => show(e, <><b>{row.label}</b><br />{g.label}: <b>{row.values[g.key]}</b></>)}
                    onMouseLeave={hide}
                    onBlur={hide}
                    className={cx('h-3 outline-none focus-visible:ring-2 focus-visible:ring-accent/40', i === shown.length - 1 && 'rounded-r')}
                    style={{ flexGrow: row.values[g.key], flexBasis: 0, background: g.color, minWidth: 3 }}
                  />
                ))}
              </span>
              <span className="num text-right text-[12px] text-ink">{total}</span>
            </li>
          )
        })}
      </ul>
      {tipNode}
    </div>
  )
}

// ── Line + area over time: one series ───────────────────────────────────────

export function TimelineChart({ points, format, height = 180 }: {
  points: { label: string; value: number }[]
  format: (label: string) => string
  height?: number
}) {
  const [box, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const pad = { l: 36, r: 12, t: 12, b: 24 }
  const w = Math.max(0, width - pad.l - pad.r)
  const h = height - pad.t - pad.b
  const max = niceMax(Math.max(1, ...points.map((p) => p.value)))
  const x = (i: number) => pad.l + (points.length > 1 ? (i / (points.length - 1)) * w : w / 2)
  const y = (v: number) => pad.t + h - (v / max) * h
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.value)}`).join(' ')
  const area = `${line} L${x(points.length - 1)},${pad.t + h} L${x(0)},${pad.t + h} Z`
  const ticks = [0, max / 2, max]
  const active = hover ?? points.length - 1

  return (
    <div ref={box} className="relative w-full">
      {width > 0 && (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Reports per week"
          onMouseMove={(e) => {
            const r = (e.currentTarget as SVGElement).getBoundingClientRect()
            const i = Math.round(((e.clientX - r.left - pad.l) / Math.max(1, w)) * (points.length - 1))
            setHover(Math.max(0, Math.min(points.length - 1, i)))
          }}
          onMouseLeave={() => setHover(null)}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={pad.l + w} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth={1} />
              <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" className="fill-faint text-[10px] tabular-nums">
                {Math.round(t).toLocaleString('en-IN')}
              </text>
            </g>
          ))}
          <path d={area} fill="var(--viz-accent)" opacity={0.1} />
          <path d={line} fill="none" stroke="var(--viz-accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {xTicks(points.length, Math.max(2, Math.floor(w / 70))).map((i) => (
            <text key={points[i].label} x={x(i)} y={height - 6} textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}
              className="fill-faint text-[10px]">{format(points[i].label)}</text>
          ))}
          <line x1={x(active)} x2={x(active)} y1={pad.t} y2={pad.t + h} stroke="var(--viz-muted)" strokeWidth={1} />
          <circle cx={x(active)} cy={y(points[active].value)} r={4.5} fill="var(--viz-accent)" stroke="var(--color-surface)" strokeWidth={2} />
        </svg>
      )}
      {width > 0 && (
        <div
          className="pointer-events-none absolute rounded-md border border-line bg-surface px-2 py-1 text-[12px] shadow-sm"
          style={{ left: Math.min(Math.max(0, x(active) - 50), width - 110), top: 0 }}
        >
          <span className="text-muted">Week of {format(points[active].label)}:</span>{' '}
          <b className="num">{points[active].value.toLocaleString('en-IN')}</b>
        </div>
      )}
    </div>
  )
}

// ── Dumbbell: before → after per place ──────────────────────────────────────

export function Dumbbell({ rows, threshold, baselineLabel, currentLabel }: {
  rows: { key: string; label: string; before: number; after: number; onClick?: () => void }[]
  threshold?: number | null
  baselineLabel: string
  currentLabel: string
}) {
  const { attach, show, hide, node: tipNode } = useTip()
  const pct = (v: number) => `${Math.max(0, Math.min(100, v))}%`
  return (
    <div ref={attach} className="relative">
      <Legend items={[
        { key: 'b', label: baselineLabel, color: 'var(--viz-muted)' },
        { key: 'a', label: currentLabel, color: 'var(--viz-accent)' },
      ]} />
      <div className="relative">
        {threshold != null && (
          // Plot column = 100% minus the 10rem label, 3rem value and two 0.5rem gaps.
          <div className="pointer-events-none absolute -top-5 bottom-0" style={{ left: `calc(10.5rem + (100% - 14rem) * ${threshold / 100})` }}>
            <div className="-translate-x-1/2 text-[10px] whitespace-nowrap text-faint">served ≥ {threshold}%</div>
            <div className="h-full w-px bg-faint/50" />
          </div>
        )}
        <ul className="space-y-1">
          {rows.map((r) => (
            <li
              key={r.key}
              tabIndex={0}
              onClick={r.onClick}
              onMouseEnter={(e) => show(e, <><b>{r.label}</b><br />{baselineLabel}: {r.before}% → {currentLabel}: <b>{r.after}%</b></>)}
              onFocus={(e) => show(e, <><b>{r.label}</b><br />{baselineLabel}: {r.before}% → {currentLabel}: <b>{r.after}%</b></>)}
              onMouseLeave={hide}
              onBlur={hide}
              className={cx('grid min-h-6 items-center gap-2 rounded text-[13px] outline-none hover:bg-subtle focus-visible:ring-2 focus-visible:ring-accent/40', r.onClick && 'cursor-pointer')}
              style={{ gridTemplateColumns: '10rem minmax(0, 1fr) 3rem' }}
            >
              <span className="truncate text-muted">{r.label}</span>
              <span className="relative h-3">
                <span
                  className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-[var(--viz-muted)]"
                  style={{ left: pct(Math.min(r.before, r.after)), width: `${Math.abs(r.after - r.before)}%` }}
                />
                <span className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--viz-muted)] ring-2 ring-surface" style={{ left: pct(r.before) }} />
                <span className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--viz-accent)] ring-2 ring-surface" style={{ left: pct(r.after) }} />
              </span>
              <span className="num text-right text-[12px] text-ink">{r.after}%</span>
            </li>
          ))}
        </ul>
      </div>
      {tipNode}
    </div>
  )
}

function niceMax(v: number): number {
  const step = 10 ** Math.floor(Math.log10(v))
  return Math.ceil(v / step) * step
}

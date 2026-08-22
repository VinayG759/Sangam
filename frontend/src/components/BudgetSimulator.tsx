import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api, type SimulationResult } from '@/api'

const STRATEGIES = [
  { id: 'equity', label: 'Equity First', desc: 'Prioritizes high-vulnerability communities' },
  { id: 'reach',  label: 'Max Reach',    desc: 'Maximizes number of citizens served' },
  { id: 'default',label: 'Highest Score', desc: 'Allocates to top-scored priorities first' },
]

const SECTOR_COLORS: Record<string, string> = {
  water:       '#38bdf8', roads: '#a78bfa', sanitation: '#34d399',
  health:      '#fb7185', education: '#fbbf24', electricity: '#60a5fa',
}

function croreLabel(n: number) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`;
  return `₹${n.toLocaleString('en-IN')}`;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; payload: { sector: string; pct_funded: number } }>;
  label?: string;
}

function SimTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  return (
    <div className="custom-tooltip">
      <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4, fontSize: 12 }}>{label}</div>
      <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{croreLabel(item.value)} allocated</div>
      <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>{item.payload.pct_funded.toFixed(0)}% of gap covered</div>
    </div>
  )
}

export default function BudgetSimulator() {
  const [budget, setBudget]     = useState(50_000_000)   // ₹5 Cr default
  const [strategy, setStrategy] = useState('equity')
  const [result, setResult]     = useState<SimulationResult | null>(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)

  async function runSim() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.simulate(budget, strategy)
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Simulation failed')
    } finally {
      setLoading(false)
    }
  }

  const chartData = result?.allocations.map(a => ({
    name: a.title.length > 20 ? a.title.slice(0, 20) + '…' : a.title,
    value: a.allocated_amount,
    sector: a.sector,
    pct_funded: a.pct_funded,
    status: a.status,
  })) ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* Controls */}
      <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700 }}>
          💰 Budget Allocation Simulator
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          Simulate how a fixed budget would be distributed across prioritized infrastructure gaps
          using different allocation strategies.
        </div>

        {/* Budget slider */}
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Available Budget: <strong style={{ color: 'var(--text-primary)' }}>{croreLabel(budget)}</strong>
          </label>
          <input
            type="range"
            min={1_000_000} max={500_000_000} step={1_000_000}
            value={budget}
            onChange={e => setBudget(Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent-blue)', cursor: 'pointer' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
            <span>₹10 L</span><span>₹25 Cr</span><span>₹50 Cr</span>
          </div>
        </div>

        {/* Strategy selector */}
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Allocation Strategy
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
            {STRATEGIES.map(s => (
              <div
                key={s.id}
                onClick={() => setStrategy(s.id)}
                style={{
                  padding: '12px 14px', borderRadius: 'var(--radius-md)',
                  border: `1px solid ${strategy === s.id ? 'var(--accent-blue)' : 'var(--border)'}`,
                  background: strategy === s.id ? 'rgba(59,110,245,0.1)' : 'var(--bg-input)',
                  cursor: 'pointer', transition: 'all var(--transition)',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, color: strategy === s.id ? 'var(--accent-blue)' : 'var(--text-primary)' }}>
                  {s.label}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>{s.desc}</div>
              </div>
            ))}
          </div>
        </div>

        <button
          className="btn btn-primary"
          onClick={runSim}
          disabled={loading}
          style={{ alignSelf: 'flex-start', minWidth: 140, justifyContent: 'center' }}
        >
          {loading ? '⟳ Running…' : '▶ Run Simulation'}
        </button>

        {error && (
          <div style={{ fontSize: 13, color: 'var(--verdict-unserved)', padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <div className="card card-pad fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Summary row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {[
              { label: 'Budget',         value: croreLabel(result.simulated_budget) },
              { label: 'Spent',          value: croreLabel(result.total_spent) },
              { label: 'Gaps Resolved',  value: String(result.gaps_fully_resolved) },
              { label: 'Citizens Helped',value: result.citizen_needs_addressed.toLocaleString('en-IN') },
            ].map(m => (
              <div key={m.label} style={{ background: 'var(--bg-input)', borderRadius: 10, padding: '12px 14px', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{m.label}</div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>{m.value}</div>
              </div>
            ))}
          </div>

          {/* Bar chart */}
          {chartData.length > 0 && (
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Allocation Breakdown</div>
              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} layout="vertical" barSize={14}>
                    <XAxis type="number" tickFormatter={v => croreLabel(v as number)} tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
                    <Tooltip content={<SimTooltip />} />
                    <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                      {chartData.map((entry, i) => (
                        <Cell key={i} fill={SECTOR_COLORS[entry.sector] ?? '#60a5fa'} opacity={entry.status === 'fully_funded' ? 1 : 0.65} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Allocation table */}
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Allocation Details</div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 4px', fontSize: 12 }}>
                <thead>
                  <tr>
                    {['Project', 'Sector', 'Allocated', '% Funded', 'Status'].map(h => (
                      <th key={h} style={{ textAlign: 'left', color: 'var(--text-muted)', fontWeight: 500, padding: '4px 10px', letterSpacing: '0.04em' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.allocations.map((a, i) => (
                    <tr key={i} style={{ background: 'var(--bg-input)' }}>
                      <td style={{ padding: '10px', borderRadius: '8px 0 0 8px', fontWeight: 500 }}>{a.title}</td>
                      <td style={{ padding: '10px', color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{a.sector}</td>
                      <td style={{ padding: '10px', fontWeight: 600 }}>{croreLabel(a.allocated_amount)}</td>
                      <td style={{ padding: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div className="progress-bar" style={{ flex: 1 }}>
                            <div className="progress-fill" style={{ width: `${a.pct_funded}%`, background: SECTOR_COLORS[a.sector] ?? 'var(--accent-blue)' }} />
                          </div>
                          <span style={{ color: 'var(--text-secondary)', minWidth: 32 }}>{a.pct_funded.toFixed(0)}%</span>
                        </div>
                      </td>
                      <td style={{ padding: '10px', borderRadius: '0 8px 8px 0' }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                          background: a.status === 'fully_funded' ? 'rgba(16,185,129,0.15)' : 'rgba(234,179,8,0.15)',
                          color: a.status === 'fully_funded' ? 'var(--verdict-wellserved)' : 'var(--verdict-underfunded)',
                        }}>
                          {a.status === 'fully_funded' ? '✓ Full' : '~ Partial'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

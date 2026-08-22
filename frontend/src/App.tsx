import { useState, useEffect } from 'react'
import './index.css'

import { api, type OverviewData, type Priority, type PackInfo, type Cluster } from '@/api'

import Header          from '@/components/Header'
import MetricCard      from '@/components/MetricCard'
import SectorChart     from '@/components/SectorChart'
import ClusterMap      from '@/components/ClusterMap'
import PriorityList    from '@/components/PriorityList'
import PriorityCard    from '@/components/PriorityCard'
import BudgetSimulator from '@/components/BudgetSimulator'
import ReportsTable    from '@/components/ReportsTable'

type Tab = 'overview' | 'priorities' | 'budget' | 'reports'

export default function App() {
  const [tab, setTab] = useState<Tab>('overview')

  // Global data
  const [pack,      setPack]      = useState<PackInfo | null>(null)
  const [overview,  setOverview]  = useState<OverviewData | null>(null)
  const [priorities,setPriorities]= useState<Priority[]>([])
  const [clusters,  setClusters]  = useState<Cluster[]>([])
  const [selected,  setSelected]  = useState<Priority | null>(null)

  // Filter state
  const [sectorFilter,  setSectorFilter]  = useState('')
  const [verdictFilter, setVerdictFilter] = useState('')

  // Loading states
  const [loadingOverview,   setLoadingOverview]   = useState(true)
  const [loadingPriorities, setLoadingPriorities] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Boot: load pack info + overview + clusters in parallel
  useEffect(() => {
    Promise.all([
      api.pack().then(setPack).catch(() => null),
      api.overview()
        .then(d => { setOverview(d); setLoadingOverview(false) })
        .catch(e => { setError(String(e)); setLoadingOverview(false) }),
      api.clusters()
        .then(setClusters)
        .catch(() => setClusters([])),
    ])
  }, [])

  // Load priorities when filter changes
  useEffect(() => {
    setLoadingPriorities(true)
    setSelected(null)
    api.priorities(sectorFilter || undefined, verdictFilter || undefined)
      .then(setPriorities)
      .catch(() => setPriorities([]))
      .finally(() => setLoadingPriorities(false))
  }, [sectorFilter, verdictFilter])

  const VERDICTS = [
    { value: '',                    label: 'All Verdicts' },
    { value: 'UNSERVED_GAP',        label: 'Unserved Gap' },
    { value: 'STALLED_ALLOCATION',  label: 'Stalled Allocation' },
    { value: 'UNDERFUNDED_CRITICAL',label: 'Underfunded Critical' },
    { value: 'WELL_SERVED',         label: 'Well Served' },
  ]

  return (
    <>
      <Header pack={pack} activeTab={tab} onTabChange={t => setTab(t as Tab)} />

      <main style={{ flex: 1, padding: '24px 0 48px' }}>
        <div className="container">

          {/* ── Error Banner ────────────────────────────────────────── */}
          {error && (
            <div style={{
              marginBottom: 20, padding: '12px 16px', borderRadius: 10,
              background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
              fontSize: 13, color: 'var(--verdict-unserved)',
            }}>
              ⚠️ Backend unreachable — {error}. Start the API with <code>docker compose up</code>.
            </div>
          )}

          {/* ── OVERVIEW TAB ─────────────────────────────────────────── */}
          {tab === 'overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

              {/* Page title */}
              <div>
                <h1 style={{ fontSize: 28, marginBottom: 6 }}>Dashboard</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                  Real-time infrastructure need intelligence from citizen reports and government expenditure data
                </p>
              </div>

              {/* Metric cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
                {loadingOverview ? (
                  [...Array(5)].map((_, i) => (
                    <div key={i} className="skeleton" style={{ height: 120, borderRadius: 'var(--radius-lg)' }} />
                  ))
                ) : overview ? (
                  <>
                    <MetricCard label="Citizen Reports"    value={overview.total_citizen_reports}      icon="📨" color="var(--accent-blue)"    delay={0} />
                    <MetricCard label="Unserved Gaps"      value={overview.unserved_gaps_count}         icon="🔴" color="var(--verdict-unserved)" delay={60} />
                    <MetricCard label="Stalled Projects"   value={overview.stalled_projects_count}      icon="⏸️" color="var(--verdict-stalled)"  delay={120} />
                    <MetricCard label="Stalled Capital"    value={overview.stalled_capital_amount}      icon="💰" color="var(--accent-amber)"    format="currency" delay={180} />
                    <MetricCard label="Total Expenditure"  value={overview.total_sanctioned_expenditure}icon="🏛️" color="var(--accent-emerald)"  format="currency" delay={240} />
                  </>
                ) : null}
              </div>

              {/* Charts row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 20 }}>
                <div className="card card-pad">
                  <h2 style={{ fontSize: 15, marginBottom: 16, fontWeight: 600 }}>Reports by Sector</h2>
                  {overview ? (
                    <SectorChart data={overview.sectors_breakdown} />
                  ) : (
                    <div className="skeleton" style={{ height: 220 }} />
                  )}
                </div>

                <div className="card card-pad">
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <h2 style={{ fontSize: 15, fontWeight: 600 }}>Issue Cluster Map</h2>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {clusters.length} clusters
                    </span>
                  </div>
                  <ClusterMap clusters={clusters} />
                </div>
              </div>

              {/* Top priorities preview */}
              <div className="card card-pad">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <h2 style={{ fontSize: 15, fontWeight: 600 }}>Top Priorities</h2>
                  <button className="btn btn-ghost" onClick={() => setTab('priorities')} style={{ fontSize: 12 }}>
                    View All →
                  </button>
                </div>
                <PriorityList
                  priorities={priorities.slice(0, 5)}
                  selectedId={selected?.id ?? null}
                  onSelect={p => { setSelected(p); setTab('priorities') }}
                  loading={loadingPriorities}
                />
              </div>
            </div>
          )}

          {/* ── PRIORITIES TAB ───────────────────────────────────────── */}
          {tab === 'priorities' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <h1 style={{ fontSize: 28, marginBottom: 4 }}>Priorities</h1>
                  <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                    {priorities.length} ranked infrastructure gaps
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <select className="select" value={sectorFilter} onChange={e => setSectorFilter(e.target.value)}>
                    <option value="">All Sectors</option>
                    {pack?.sectors.map(s => <option key={s.key} value={s.key}>{s.name}</option>)}
                  </select>
                  <select className="select" value={verdictFilter} onChange={e => setVerdictFilter(e.target.value)}>
                    {VERDICTS.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 1fr' : '1fr', gap: 20, alignItems: 'start' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                  <PriorityList
                    priorities={priorities}
                    selectedId={selected?.id ?? null}
                    onSelect={p => setSelected(p === selected ? null : p)}
                    loading={loadingPriorities}
                  />
                </div>

                {selected && (
                  <div className="fade-up" style={{ position: 'sticky', top: 80, maxHeight: 'calc(100vh - 100px)', overflowY: 'auto' }}>
                    <PriorityCard priority={selected} />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── BUDGET SIM TAB ───────────────────────────────────────── */}
          {tab === 'budget' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div>
                <h1 style={{ fontSize: 28, marginBottom: 4 }}>Budget Simulator</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                  Model the impact of infrastructure investment across different allocation strategies
                </p>
              </div>
              <BudgetSimulator />
            </div>
          )}

          {/* ── REPORTS TAB ──────────────────────────────────────────── */}
          {tab === 'reports' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div>
                <h1 style={{ fontSize: 28, marginBottom: 4 }}>Citizen Reports</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                  Browse and explore translated citizen voice reports
                </p>
              </div>
              <ReportsTable pack={pack} />
            </div>
          )}

        </div>
      </main>

      {/* Footer */}
      <footer style={{
        borderTop: '1px solid var(--border)', padding: '16px 0',
        background: 'var(--bg-surface)',
      }}>
        <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Sangam · Digital Public Good for Evidence-Backed Infrastructure Prioritization
          </span>
          {pack && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Active Pack: {pack.country_code} — {pack.region_name}
            </span>
          )}
        </div>
      </footer>
    </>
  )
}

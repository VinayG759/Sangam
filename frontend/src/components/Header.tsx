import type { PackInfo } from '@/api'
import { LayoutGridIcon, ListRankedIcon, SlidersIcon, FileTextIcon } from '@/components/icons'

interface HeaderProps {
  pack: PackInfo | null;
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const tabs = [
  { id: 'overview',   label: 'Overview',   icon: <LayoutGridIcon /> },
  { id: 'priorities', label: 'Priorities', icon: <ListRankedIcon /> },
  { id: 'budget',     label: 'Budget Sim', icon: <SlidersIcon /> },
  { id: 'reports',    label: 'Reports',    icon: <FileTextIcon /> },
]

export default function Header({ pack, activeTab, onTabChange }: HeaderProps) {
  return (
    <header style={{
      position: 'sticky',
      top: 0,
      zIndex: 100,
      borderBottom: '1px solid var(--border)',
      background: 'rgba(6, 13, 26, 0.85)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
    }}>
      <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 64, gap: 24 }}>

        {/* Logo + name */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div style={{
            width: 34, height: 34, borderRadius: '50%',
            background: 'var(--grad-brand)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, fontWeight: 800, color: '#fff',
            boxShadow: '0 0 16px rgba(59,110,245,0.5)',
          }}>S</div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 17, lineHeight: 1 }}>Sangam</div>
            {pack && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                {pack.region_name}
              </div>
            )}
          </div>
        </div>

        {/* Tab navigation */}
        <nav className="tab-bar" style={{ flex: 1, maxWidth: 480 }}>
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`tab-btn${activeTab === tab.id ? ' active' : ''}`}
              onClick={() => onTabChange(tab.id)}
            >
              <span style={{ display: 'inline-flex' }}>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Pack info pill */}
        {pack && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 12px', borderRadius: 999,
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            fontSize: 11, color: 'var(--text-muted)',
            flexShrink: 0,
          }}>
            {pack.country_code} · {pack.sectors.length} sectors
          </div>
        )}
      </div>
    </header>
  )
}

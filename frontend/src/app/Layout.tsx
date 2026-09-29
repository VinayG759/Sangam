import { NavLink, Outlet, ScrollRestoration } from 'react-router'
import { Activity, Calculator, ChartColumn, LayoutGrid, ListOrdered, Map as MapIcon, MessageSquareText, Send, ShieldCheck } from 'lucide-react'
import { usePack } from '@/lib/pack'
import { useOverview } from '@/features/overview/api'
import { cx } from '@/lib/cx'
import { DemoTag } from '@/ui/DemoTag'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutGrid, end: true },
  { to: '/analytics', label: 'Analytics', icon: ChartColumn },
  { to: '/priorities', label: 'Priorities', icon: ListOrdered },
  { to: '/map', label: 'Map', icon: MapIcon },
  { to: '/simulator', label: 'Budget simulator', icon: Calculator },
  { to: '/impact', label: 'Impact', icon: Activity },
  { to: '/reports', label: 'Citizen reports', icon: MessageSquareText },
  { to: '/verify', label: 'Verify a brief', icon: ShieldCheck },
]

function navClass({ isActive }: { isActive: boolean }) {
  return cx(
    'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors whitespace-nowrap',
    isActive ? 'bg-subtle font-medium text-ink' : 'text-muted hover:bg-subtle hover:text-ink',
  )
}

export function Layout() {
  const pack = usePack()
  const overview = useOverview('') // whole country: the demo-data notice is not region-specific
  const synthetic = overview.data?.reports.synthetic ?? 0

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="shrink-0 border-b border-line bg-surface md:w-56 md:border-r md:border-b-0">
        <div className="flex flex-col gap-4 p-3 md:sticky md:top-0 md:h-screen md:p-4">
          <div className="flex items-center gap-2 px-1">
            <img src="/favicon.svg" alt="" className="size-6" />
            <div className="leading-tight">
              <div className="text-[14px] font-semibold">Sangam</div>
              <div className="text-[11px] text-faint">{pack.data?.country_name ?? ' '}</div>
            </div>
          </div>
          <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto px-1 md:mx-0 md:flex-col md:overflow-visible md:px-0">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={navClass}>
                <Icon className="size-4 shrink-0" strokeWidth={1.75} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto hidden space-y-3 md:block">
            <a href="/report" className="flex items-center gap-2 rounded-md border border-line px-2.5 py-2 text-[12px] text-muted hover:text-ink">
              <Send className="size-3.5" strokeWidth={1.75} />
              Citizen report form
            </a>
            <p className="px-1 text-[11px] leading-relaxed text-faint">
              Open-source Digital Public Good. Rankings are arithmetic; AI only writes explanations.
            </p>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        {synthetic > 0 && (
          <div className="border-b border-line bg-subtle px-4 py-2 text-[12px] text-muted md:px-8">
            <span className="font-medium text-ink">Prototype with demonstration data.</span>{' '}
            The {synthetic.toLocaleString('en-IN')} citizen reports, the public projects, and the statistics for needs
            other than water are synthetic, and marked <DemoTag inline />. Places, households and water tap coverage are
            real government data. Every verdict and ranking is computed by the real engine.
          </div>
        )}
        <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </div>
      </main>
      <ScrollRestoration />
    </div>
  )
}

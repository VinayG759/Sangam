import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, ScrollRestoration, useLocation } from 'react-router'
import {
  Activity, Calculator, ChartColumn, LayoutGrid, ListOrdered, Map as MapIcon, Menu, MessageSquareText, Send,
  SearchCheck, ShieldCheck, X,
} from 'lucide-react'
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
    'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[14px] transition-colors md:py-1.5 md:text-[13px]',
    isActive ? 'bg-subtle font-medium text-ink' : 'text-muted hover:bg-subtle hover:text-ink',
  )
}

function Brand({ country }: { country?: string }) {
  return (
    <div className="flex items-center gap-2 px-1">
      <img src="/favicon.svg" alt="" className="size-6" />
      <div className="leading-tight">
        <div className="text-[14px] font-semibold">Sangam</div>
        <div className="text-[11px] text-faint">{country ?? ' '}</div>
      </div>
    </div>
  )
}

/** Navigation and footer, shared by the desktop sidebar and the phone drawer. */
function NavContent() {
  return (
    <>
      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={navClass}>
            <Icon className="size-4 shrink-0" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto space-y-3">
        <a href="/report" className="flex items-center gap-2 rounded-md border border-line px-2.5 py-2 text-[12px] text-muted hover:text-ink">
          <Send className="size-3.5" strokeWidth={1.75} />
          Citizen report form
        </a>
        <a href="/track" className="flex items-center gap-2 rounded-md border border-line px-2.5 py-2 text-[12px] text-muted hover:text-ink">
          <SearchCheck className="size-3.5" strokeWidth={1.75} />
          Track a report
        </a>
        <p className="px-1 text-[11px] leading-relaxed text-faint">
          Open-source Digital Public Good. Rankings are arithmetic; AI only writes explanations.
        </p>
      </div>
    </>
  )
}

export function Layout() {
  const pack = usePack()
  const overview = useOverview('') // whole country: the demo-data notice is not region-specific
  const synthetic = overview.data?.reports.synthetic ?? 0
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const current = NAV.find((n) => (n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)))

  // Picking a page closes the menu.
  const [lastPath, setLastPath] = useState(location.pathname)
  if (lastPath !== location.pathname) {
    setLastPath(location.pathname)
    setMenuOpen(false)
  }

  // While open: Escape closes it, the page behind does not scroll, focus moves into the menu and back out.
  useEffect(() => {
    if (!menuOpen) return
    const button = menuButton.current
    closeButton.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false)
    window.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      button?.focus()
    }
  }, [menuOpen])

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {/* Desktop and tablet: a fixed sidebar. */}
      <aside className="hidden shrink-0 border-r border-line bg-surface md:block md:w-56">
        <div className="sticky top-0 flex h-screen flex-col gap-4 p-4">
          <Brand country={pack.data?.country_name} />
          <NavContent />
        </div>
      </aside>

      {/* Phones: a slim top bar with a menu button. */}
      <header className="sticky top-0 z-[1050] flex items-center justify-between gap-3 border-b border-line bg-surface px-3 py-2 md:hidden">
        <Brand country={pack.data?.country_name} />
        <div className="flex min-w-0 items-center gap-2">
          {current && <span className="truncate text-[13px] text-muted">{current.label}</span>}
          <button
            ref={menuButton}
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            className="inline-flex size-10 items-center justify-center rounded-md text-ink hover:bg-subtle"
          >
            <Menu className="size-5" />
            <span className="sr-only">Open menu</span>
          </button>
        </div>
      </header>

      {/* Phones: the menu slides in from the left, over a dimmed page. */}
      <div className={cx('fixed inset-0 z-[1100] md:hidden', !menuOpen && 'pointer-events-none')} aria-hidden={!menuOpen}>
        <div
          className={cx('absolute inset-0 bg-black/40 transition-opacity duration-200', menuOpen ? 'opacity-100' : 'opacity-0')}
          onClick={() => setMenuOpen(false)}
        />
        <div
          id="mobile-menu"
          role="dialog"
          aria-modal="true"
          aria-label="Menu"
          inert={!menuOpen}
          className={cx(
            'absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col gap-4 overflow-y-auto bg-surface p-4 shadow-xl transition-transform duration-200 motion-reduce:transition-none',
            menuOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <div className="flex items-center justify-between">
            <Brand country={pack.data?.country_name} />
            <button
              ref={closeButton}
              type="button"
              onClick={() => setMenuOpen(false)}
              className="inline-flex size-10 items-center justify-center rounded-md text-muted hover:bg-subtle hover:text-ink"
            >
              <X className="size-5" />
              <span className="sr-only">Close menu</span>
            </button>
          </div>
          <NavContent />
        </div>
      </div>

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

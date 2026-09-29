import type { ReactNode } from 'react'

export interface Source {
  name: string | null
  url?: string | null
  period?: string | null
}

/**
 * A number with its source. Every figure a policymaker sees carries a marker;
 * hovering or focusing it shows where the number came from.
 */
export function Figure({ children, source }: { children: ReactNode; source?: Source | null }) {
  if (!source?.name) return <span className="num">{children}</span>
  const label = [source.name, source.period].filter(Boolean).join(' · ')
  return (
    <span className="group relative inline-flex items-baseline gap-0.5">
      <span className="num">{children}</span>
      <button
        type="button"
        aria-label={`Source: ${label}`}
        className="relative -top-1 size-3.5 rounded-full border border-line text-[8px] leading-none text-faint hover:border-accent hover:text-accent focus:border-accent focus:text-accent"
      >
        i
      </button>
      <span
        role="tooltip"
        // display:none (not visibility) so a hidden tooltip never widens the page on small screens
        className="pointer-events-none absolute right-0 bottom-full z-20 mb-1.5 hidden w-64 max-w-[80vw] rounded-md border border-line bg-surface p-2.5 text-left text-[12px] font-normal leading-snug text-muted shadow-sm group-focus-within:block group-hover:block"
      >
        <span className="block text-ink">{source.name}</span>
        {source.period && <span className="block">Period: {source.period}</span>}
        {source.url && <span className="mt-1 block break-all text-accent">{source.url}</span>}
      </span>
    </span>
  )
}

import { type ReactNode, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export interface Source {
  name: string | null
  url?: string | null
  period?: string | null
}

const TIP_WIDTH = 256

/**
 * A number with its source. Every figure a policymaker sees carries a marker;
 * hovering or focusing it shows where the number came from.
 *
 * The tooltip is drawn at the top level of the page (a portal), positioned from the
 * marker's place on screen, so scroll boxes and sticky table headers can never hide it.
 */
export function Figure({ children, source }: { children: ReactNode; source?: Source | null }) {
  const button = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ left: number; top: number; below: boolean } | null>(null)

  useLayoutEffect(() => {
    if (!open || !button.current) return
    const place = () => {
      const r = button.current!.getBoundingClientRect()
      const below = r.top < 120 // not enough room above: open underneath
      const left = Math.min(Math.max(8, r.right - TIP_WIDTH), window.innerWidth - TIP_WIDTH - 8)
      setPos({ left, top: below ? r.bottom + 6 : r.top - 6, below })
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open])

  if (!source?.name) return <span className="num">{children}</span>
  const label = [source.name, source.period].filter(Boolean).join(' · ')
  return (
    <span className="inline-flex items-baseline gap-0.5">
      <span className="num">{children}</span>
      <button
        ref={button}
        type="button"
        aria-label={`Source: ${label}`}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)} // touch screens have no hover
        className="relative -top-1 size-3.5 rounded-full border border-line text-[8px] leading-none text-faint hover:border-accent hover:text-accent focus:border-accent focus:text-accent"
      >
        i
      </button>
      {open && pos && createPortal(
        <span
          role="tooltip"
          className="pointer-events-none fixed z-[1000] rounded-md border border-line bg-surface p-2.5 text-left text-[12px] font-normal leading-snug text-muted shadow-lg"
          style={{ left: pos.left, top: pos.top, width: TIP_WIDTH, maxWidth: 'calc(100vw - 16px)', transform: pos.below ? undefined : 'translateY(-100%)' }}
        >
          <span className="block text-ink">{source.name}</span>
          {source.period && <span className="block">Period: {source.period}</span>}
          {source.url && <span className="mt-1 block break-all text-accent">{source.url}</span>}
        </span>,
        document.body,
      )}
    </span>
  )
}

import type { ReactNode } from 'react'
import { cx } from '@/lib/cx'

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('animate-pulse rounded-md bg-subtle', className)} />
}

export function ErrorState({ error, title = 'Could not load this' }: { error: unknown; title?: string }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="rounded-lg border border-line bg-surface p-6">
      <div className="font-medium">{title}</div>
      <p className="mt-1 text-muted">{message}</p>
      <p className="mt-2 text-[12px] text-faint">Other pages are unaffected. Try reloading, or check that the API is running.</p>
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-8 text-center">
      <div className="font-medium">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-md text-muted">{children}</div>}
    </div>
  )
}

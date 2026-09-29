import type { ComponentProps, ReactNode } from 'react'
import { Link } from 'react-router'
import { cx } from '@/lib/cx'


export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}

export function Panel({ title, actions, children, className, flush }: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  flush?: boolean
}) {
  return (
    <section className={cx('min-w-0 rounded-lg border border-line bg-surface', className)}>
      {title && (
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 border-b border-line px-4 py-3">
          <h2 className="min-w-0 text-[13px] font-semibold">{title}</h2>
          {actions}
        </div>
      )}
      <div className={flush ? '' : 'p-4'}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, to }: { label: string; value: ReactNode; hint?: ReactNode; to?: string }) {
  const body = (
    <>
      <div className="text-[12px] text-muted">{label}</div>
      <div className="num mt-1 text-2xl font-semibold tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-[12px] text-faint">{hint}</div>}
    </>
  )
  const style = 'block rounded-lg border border-line bg-surface p-4'
  return to ? (
    <Link to={to} className={cx(style, 'transition-colors hover:border-faint')}>
      {body}
    </Link>
  ) : (
    <div className={style}>{body}</div>
  )
}

type ButtonProps = ComponentProps<'button'> & { variant?: 'primary' | 'secondary' }

export function Button({ variant = 'secondary', className, ...props }: ButtonProps) {
  return (
    <button
      className={cx(
        'inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-[13px] font-medium transition-colors disabled:opacity-50',
        variant === 'primary'
          ? 'bg-accent text-white hover:opacity-90'
          : 'border border-line bg-surface text-ink hover:bg-subtle',
        className,
      )}
      {...props}
    />
  )
}

export function ButtonLink({ href, children, variant = 'secondary' }: { href: string; children: ReactNode; variant?: 'primary' | 'secondary' }) {
  return (
    <a
      href={href}
      className={cx(
        'inline-flex h-9 items-center gap-2 rounded-md px-3 text-[13px] font-medium transition-colors',
        variant === 'primary' ? 'bg-accent text-white hover:opacity-90' : 'border border-line bg-surface hover:bg-subtle',
      )}
    >
      {children}
    </a>
  )
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: ReactNode }[]
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-md border border-line bg-surface p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cx(
            'h-8 shrink-0 rounded px-3 text-[13px] whitespace-nowrap transition-colors',
            value === option.value ? 'bg-subtle text-ink' : 'text-muted hover:text-ink',
          )}
        >
          {/* An invisible bold copy reserves the selected width, so switching never shifts the labels. */}
          <span className="grid">
            <span aria-hidden className="invisible col-start-1 row-start-1 font-medium">{option.label}</span>
            <span className={cx('col-start-1 row-start-1', value === option.value && 'font-medium')}>{option.label}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx('inline-flex items-center rounded border border-line px-1.5 py-px text-[11px] text-muted', className)}>
      {children}
    </span>
  )
}

export const inputStyle =
  'h-9 rounded-md border border-line bg-surface px-3 text-[13px] text-ink placeholder:text-faint focus:border-accent focus:outline-none'

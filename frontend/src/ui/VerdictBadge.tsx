import type { Verdict } from '@/lib/api'
import { VERDICTS } from '@/lib/verdicts'
import { cx } from '@/lib/cx'

export function VerdictBadge({ verdict, withAction }: { verdict: Verdict; withAction?: boolean }) {
  const meta = VERDICTS[verdict]
  return (
    <span
      title={meta.meaning}
      className={cx('inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 py-0.5 text-[12px] font-medium', meta.soft, meta.text)}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {meta.label}
      {withAction && <span className="font-normal opacity-80">· {meta.action}</span>}
    </span>
  )
}

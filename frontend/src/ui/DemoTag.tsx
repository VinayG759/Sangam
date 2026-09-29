/** Marks a figure as made-up demonstration data. */
export function DemoTag({ inline }: { inline?: boolean }) {
  return (
    <span
      title="Synthetic demonstration data, not a government record"
      className={`${inline ? '' : 'ml-1.5 '}inline-block rounded border border-line px-1 align-middle text-[10px] font-medium uppercase tracking-wide text-faint`}
    >
      demo
    </span>
  )
}

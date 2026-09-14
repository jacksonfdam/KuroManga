/**
 * One number with its name above it and, where the number needs one, the
 * sentence that says what it is made of. Every figure on this screen is drawn
 * this way so that a caption can never end up belonging to the wrong number.
 */
export function Figure({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  /** Only ever a fact the payload carries. A figure whose sub-line is invented
      is worse than a figure with no sub-line at all. */
  detail?: string | null
}) {
  return (
    <div className="flex min-w-0 flex-col gap-space-xs">
      <span className="font-mono text-label-sm uppercase tracking-wide text-outline">{label}</span>
      <span className="text-headline-md text-on-surface">{value}</span>
      {detail && <span className="text-body-sm text-on-surface-variant">{detail}</span>}
    </div>
  )
}

// Tailwind's scanner reads this file as text and never evaluates `bg-${tone}` —
// an interpolated class is invisible to it, so the bar rendered uncoloured at
// every tone until this became a literal lookup, the same way StatusPill's
// TINT record already does it.
const FILL: Record<'primary' | 'secondary' | 'tertiary' | 'warning' | 'error', string> = {
  primary: 'bg-primary',
  secondary: 'bg-secondary',
  tertiary: 'bg-tertiary',
  warning: 'bg-warning',
  error: 'bg-error',
}

export function ProgressBar({
  value,
  max,
  tone = 'secondary',
}: {
  value: number
  max: number
  tone?: keyof typeof FILL
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-surface-container-highest">
      <div className={`h-full rounded-full ${FILL[tone]} transition-[width] duration-300`} style={{ width: `${pct}%` }} />
    </div>
  )
}

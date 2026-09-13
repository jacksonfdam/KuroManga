export function ProgressBar({ value, max, tone = 'secondary' }: { value: number; max: number; tone?: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-surface-container-highest">
      <div className={`h-full rounded-full bg-${tone} transition-[width] duration-300`} style={{ width: `${pct}%` }} />
    </div>
  )
}

/**
 * No mockup depicts a loading state — all six render a fully-loaded screen —
 * so this composes the same surface/radius tokens the rest of the system uses
 * rather than transcribing a one-off shape.
 */
export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-surface-container-high ${className}`} />
}

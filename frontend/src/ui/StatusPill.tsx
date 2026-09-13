import { STATUS_LABEL, STATUS_TONE, type ListStatus } from '../lib/format'

const TINT: Record<string, string> = {
  secondary: 'bg-secondary/10 text-secondary',
  primary: 'bg-primary/10 text-primary',
  tertiary: 'bg-tertiary/10 text-tertiary',
  warning: 'bg-warning/10 text-warning',
  error: 'bg-error/10 text-error',
}

export function StatusPill({ status }: { status: ListStatus }) {
  const tone = STATUS_TONE[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-space-sm py-0.5 font-mono text-label-sm ${TINT[tone]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {STATUS_LABEL[status]}
    </span>
  )
}

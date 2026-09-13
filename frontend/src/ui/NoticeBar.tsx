import { Button } from './Button'

const TONE: Record<string, string> = {
  info: 'bg-surface-container text-on-surface-variant',
  error: 'bg-error-container/20 text-error',
}

/**
 * A one-line outcome above a screen's content: a refresh that failed while the
 * page stayed valid, or a control reporting what its click did. An error is
 * announced rather than merely displayed — the control that triggered it keeps
 * focus, so nothing else would tell a screen reader the click failed.
 */
export function NoticeBar({
  tone = 'info',
  text,
  onRetry,
}: {
  tone?: 'info' | 'error'
  text: string
  onRetry?: () => void
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex flex-wrap items-center justify-between gap-space-sm rounded-xl px-space-md py-space-sm text-body-sm ${TONE[tone]}`}
    >
      <span>{text}</span>
      {onRetry && (
        <Button variant="surface" size="sm" icon="sync" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

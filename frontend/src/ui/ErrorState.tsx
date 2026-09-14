import { Button } from './Button'
import { EmptyState } from './EmptyState'

/**
 * The first request for a screen failed and there is nothing to fall back to.
 * Deliberately not EmptyState: "there is nothing here" and "we could not find
 * out what is here" are different facts, and every screen but one used to show
 * the first when it meant the second — a dead API read as an empty library.
 */
export function ErrorState({
  title = "Couldn't load this screen",
  detail,
  onRetry,
}: {
  title?: string
  detail: string
  onRetry: () => void
}) {
  return (
    <EmptyState
      icon="warning"
      title={title}
      detail={detail}
      action={
        <Button variant="surface" icon="sync" onClick={onRetry}>
          Retry
        </Button>
      }
    />
  )
}

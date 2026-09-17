import { Icon } from './Icon'
import { useIncrementFlash, type FlashState } from './useIncrementFlash'

// Markup reference: the `quick-plus-btn` overlay in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
// The 400ms flash is the only feedback a one-click control gets, so success
// and rejection have to look different rather than both reverting silently.
//
// It lives here rather than under the library, because Home offers the same
// click on its own continue-reading cards and a feature folder may not import
// another. A second copy is how the rejection flash was lost once already.
const FLASH: Record<NonNullable<FlashState>, string> = {
  success: 'bg-secondary text-on-secondary border-secondary',
  error: 'bg-error text-on-error border-error',
}

// Tertiary is the pipeline's in-flight tone everywhere else (the table's
// "Downloading" pill, the Komga chip), so a chapter still travelling to the
// providers wears it too rather than inventing a fourth colour.
const PENDING = 'border-tertiary/40 bg-tertiary/[0.12] text-tertiary'

// Said once, for every screen that offers a write. The table row and the
// series detail stepper are not this component, but they refuse for the
// same reason and must not word it differently.
// Named the cause wrongly: it blamed a read-only provider, when every provider
// here can be written to and the real state is that no list holds this series
// at all. A message pointing at the wrong reason sends the reader to check a
// setting that was never the problem.
export const NO_WRITE_TARGET = 'No list holds this series yet, so there is nowhere to record a chapter'

export function QuickIncrement({
  progress,
  pending = false,
  writable = true,
  onIncrement,
}: {
  progress: number
  /**
   * The queue took a chapter and no worker has written it yet. The button
   * stays live: a second click raises the chapter on the job already waiting
   * rather than queueing a competing one.
   */
  pending?: boolean
  /**
   * Whether a write has anywhere to land. A series held only by providers the
   * pipeline cannot write to — one that is read-only, or one whose credential
   * was never configured — fails every progress write with "no connected list
   * entry", so the control says so before the click rather than flashing red
   * after it.
   *
   * The wording lives here rather than at each caller: four screens offer this
   * button, and four copies of one sentence is how they start disagreeing.
   */
  writable?: boolean
  onIncrement: (next: number) => Promise<void>
}) {
  const { flash, busy, trigger } = useIncrementFlash(onIncrement)

  return (
    <button
      type="button"
      // Both callers sit inside a link to the series, so a bare handler marks
      // the chapter read and then navigates away from the card the reader was
      // watching the number change on.
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
        void trigger(progress + 1)
      }}
      disabled={busy || !writable}
      aria-label={writable ? 'Mark next chapter read' : NO_WRITE_TARGET}
      title={
        !writable
          ? NO_WRITE_TARGET
          : pending
            ? 'Waiting for the write to reach your lists'
            : 'Mark next chapter read'
      }
      className={`flex h-8 w-8 items-center justify-center rounded-lg border border-white/15 bg-surface-container/85 text-on-surface backdrop-blur transition-all active:scale-90 disabled:cursor-not-allowed ${
        // The flash outranks the pending tint for its 400ms: it is the answer
        // to the click that just happened, and pending is the state around it.
        flash ? FLASH[flash] : pending ? PENDING : 'hover:bg-primary hover:text-on-primary'
      }`}
    >
      <Icon name={pending && !flash ? 'sync' : 'add'} className="h-4 w-4" />
    </button>
  )
}

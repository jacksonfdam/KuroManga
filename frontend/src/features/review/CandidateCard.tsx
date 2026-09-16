import { Button, ProgressBar } from '../../ui'
import type { Candidate } from '../../lib/api'

// No mockup covers this screen, so the layout is built from the library
// screen's row conventions (ContinueReading's cover-plus-metadata row) rather
// than a reference render. The one deliberate departure: confirming a match
// is one of the pipeline's two stops — a wrong one downloads the wrong manga
// for every future chapter — so the primary button is a real anchor on the
// right, not a corner link riding along on a clickable card.
export function CandidateCard({
  candidate,
  index,
  disabled,
  onConfirm,
}: {
  candidate: Candidate
  index: number
  disabled: boolean
  onConfirm: () => void
}) {
  const scorePct = Math.round(candidate.score * 100)

  return (
    <div className="flex flex-col gap-4 rounded-xl bg-surface-container-low p-4 shadow-card sm:flex-row sm:items-center">
      <div className="relative h-28 w-20 shrink-0 self-start overflow-hidden rounded-lg bg-surface-container-highest shadow-sm sm:self-center">
        {candidate.cover_url && (
          <img src={candidate.cover_url} alt="" className="h-full w-full object-cover" />
        )}
        {/* Mirrors the review queue's own 1-9 shortcut, so the number on the
            card is the same key that confirms it. */}
        {index < 9 && (
          <span className="absolute left-1 top-1 flex h-5 w-5 items-center justify-center rounded bg-surface-container-lowest/85 font-mono text-label-sm font-bold text-on-surface-variant backdrop-blur-md">
            {index + 1}
          </span>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {/* Titles here run to a couple of hundred characters - a doujinshi's
            full subtitle chain is normal on MangaDex - and truncating to one
            line hid the part that distinguishes one candidate from the next,
            which is the whole judgement this screen asks for. Three lines is
            enough to tell them apart and bounded enough that one absurd title
            cannot own the list. Aligned to the start so the source badge rides
            with the first line instead of the middle of a three-line block. */}
        <div className="flex flex-wrap items-start gap-2">
          <h3 className="line-clamp-3 text-body-md font-bold text-on-surface">
            {candidate.title}
          </h3>
          <span className="mt-0.5 shrink-0 rounded bg-primary/10 px-1.5 py-0.5 font-mono text-label-sm text-primary">
            {candidate.source_site}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-mono text-body-sm text-outline">
          {candidate.year && <span>{candidate.year}</span>}
          {candidate.chapter_count ? <span>{candidate.chapter_count} ch</span> : null}
        </div>
        <div className="flex items-center gap-2">
          <div className="w-32 max-w-full">
            <ProgressBar value={scorePct} max={100} tone="tertiary" />
          </div>
          <span className="font-mono text-label-sm text-outline">{scorePct}% match</span>
        </div>
      </div>

      <Button
        variant="primary"
        icon="check"
        disabled={disabled}
        onClick={onConfirm}
        className="w-full shrink-0 justify-center sm:w-auto"
      >
        Confirm match
      </Button>
    </div>
  )
}

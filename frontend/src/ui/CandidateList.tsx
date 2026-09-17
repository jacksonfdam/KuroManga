/** A source the search found, from whichever of the three shapes served it. */
export interface SourceChoice {
  url: string
  site: string
  score: number
  title?: string | null
  cover_url?: string | null
  chapters?: number | null
  year?: number | null
}

/**
 * The sources found for a series, and the one the reader picks.
 *
 * This list only ever existed on the Review screen. Retiring that screen took
 * it with it, and left the series page offering a search whose results it
 * never showed and a sentence pointing at a screen that no longer exists. It
 * lives in `ui/` now because three places show it and a feature folder may not
 * import another.
 *
 * What choosing means is the caller's: on the series page it confirms the
 * mapping, and on an unadded suggestion it marks the source to confirm once
 * the series exists.
 */
export function CandidateList({
  candidates,
  chosen,
  busy = false,
  onChoose,
}: {
  candidates: SourceChoice[]
  /** The picked source's URL, when picking and acting are two steps. */
  chosen?: string | null
  busy?: boolean
  onChoose: (candidate: SourceChoice) => void
}) {
  return (
    <ul className="flex flex-col gap-space-xs">
      {candidates.map((candidate) => {
        const picked = chosen === candidate.url
        return (
          <li key={candidate.url}>
            <button
              type="button"
              disabled={busy}
              onClick={() => onChoose(candidate)}
              aria-pressed={picked}
              className={`flex w-full items-center gap-space-sm rounded-lg p-space-xs text-left transition-colors disabled:opacity-50 ${
                picked
                  ? 'bg-primary/20 ring-1 ring-primary'
                  : 'bg-surface-container-low hover:bg-surface-container-high'
              }`}
            >
              <div className="h-12 w-8 shrink-0 overflow-hidden rounded bg-surface-container-highest">
                {candidate.cover_url && (
                  <img
                    src={candidate.cover_url}
                    alt=""
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                )}
              </div>
              <div className="flex min-w-0 flex-col">
                {/* The address is the fallback, not the site: suggestions
                    recorded before titles were stored have several results
                    from one site, and "mangadex" three times over is not a
                    choice anyone can make. */}
                <span className="truncate text-body-sm text-on-surface">
                  {candidate.title || candidate.url}
                </span>
                {/* Every figure here is one the API served. A candidate that
                    states no chapter count and no year says neither, rather
                    than showing a zero that reads as a fact. */}
                <span className="truncate font-mono text-label-sm text-outline">
                  {[
                    candidate.site,
                    candidate.chapters ? `${candidate.chapters} ch` : null,
                    candidate.year ? String(candidate.year) : null,
                    `${Math.round(candidate.score * 100)}%`,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

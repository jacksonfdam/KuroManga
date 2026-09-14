import { AddToList, ProgressBar } from '../../ui'
import type { SearchCandidate } from '../../lib/api'
import type { ListStatus } from '../../lib/format'
import { FORMAT_LABELS, KNOWN_STATES, PUBLISHING_LABELS, providerName } from './labels'
import type { Choice } from './useUnmatched'

export function SearchCandidateCard({
  candidate,
  cardKey,
  choice,
  busy,
  onStatus,
  onDownload,
  onAdd,
}: {
  candidate: SearchCandidate
  cardKey: string
  choice: Choice
  busy: boolean
  onStatus: (status: ListStatus) => void
  onDownload: (download: boolean) => void
  onAdd: () => void
}) {
  const known = candidate.known_state ? KNOWN_STATES[candidate.known_state] : undefined
  const blocked = known?.blocks ?? false
  const scorePct = Math.round(candidate.score * 100)

  return (
    <article className="flex gap-space-md rounded-xl bg-surface-container-low p-space-md shadow-card">
      <div className="aspect-[2/3] w-16 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest">
        {candidate.cover_url && (
          <img
            src={candidate.cover_url}
            alt={`Cover of ${candidate.title}`}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-space-sm">
        <h4 className="text-body-md font-bold text-on-surface">{candidate.title}</h4>
        <div className="flex flex-wrap items-center gap-space-xs">
          <span
            className={`rounded-full px-space-sm py-0.5 font-mono text-label-sm ${
              candidate.format
                ? 'bg-tertiary/[0.12] text-tertiary'
                : 'bg-warning/[0.12] text-warning'
            }`}
            title={
              candidate.format
                ? undefined
                : 'Neither provider said what this is. It may not be a manga — check before you add it.'
            }
          >
            {candidate.format
              ? (FORMAT_LABELS[candidate.format] ?? candidate.format)
              : 'Type not stated'}
          </span>
          {candidate.publishing_status && (
            <span className="rounded-full bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm text-on-surface-variant">
              {PUBLISHING_LABELS[candidate.publishing_status] ?? candidate.publishing_status}
            </span>
          )}
          {candidate.providers.map((provider) => (
            <span
              key={provider}
              className="rounded-full bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm text-on-surface-variant"
            >
              {providerName(provider)}
            </span>
          ))}
          {known && (
            <span className={`rounded-full px-space-sm py-0.5 font-mono text-label-sm ${known.tint}`}>
              {known.label}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-space-md font-mono text-label-sm text-outline">
          {candidate.year && <span>{candidate.year}</span>}
          <span>
            {candidate.total_chapters
              ? `${candidate.total_chapters} chapters`
              : 'chapter count unknown'}
          </span>
        </div>
        <div className="flex items-center gap-space-sm">
          <div className="w-28 max-w-full">
            <ProgressBar value={scorePct} max={100} tone="tertiary" />
          </div>
          <span className="font-mono text-label-sm text-outline">{scorePct}% match</span>
        </div>
        {known && <p className="text-body-sm text-on-surface-variant">{known.note}</p>}
        <AddToList
          idPrefix={cardKey}
          status={choice.status}
          download={choice.download}
          disabled={blocked}
          busy={busy}
          addLabel={blocked ? 'Already added' : 'Add'}
          onStatus={onStatus}
          onDownload={onDownload}
          onAdd={onAdd}
        />
      </div>
    </article>
  )
}

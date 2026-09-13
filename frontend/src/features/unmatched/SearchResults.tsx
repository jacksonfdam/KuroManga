import type { SearchCandidate, UnmatchedAnime, UnmatchedSearch } from '../../lib/api'
import type { ListStatus } from '../../lib/format'
import { SearchCandidateCard } from './SearchCandidateCard'
import { candidateKey, errorMessage, providerName, substitutedQueries } from './labels'
import type { Choice } from './useUnmatched'

export function SearchResults({
  anime,
  found,
  busy,
  settingFor,
  onStatus,
  onDownload,
  onAdd,
}: {
  anime: UnmatchedAnime
  found: UnmatchedSearch
  busy: string | null
  settingFor: (key: string) => Choice
  onStatus: (key: string, status: ListStatus) => void
  onDownload: (key: string, download: boolean) => void
  onAdd: (candidate: SearchCandidate) => void
}) {
  return (
    <div className="flex flex-col gap-space-sm border-t border-surface-container-high pt-space-md">
      {/* A provider that failed is reported beside the other's results, never
          instead of them. */}
      {found.errors.map((failure) => (
        <p key={failure.provider} className="text-body-sm text-error" title={failure.detail}>
          {errorMessage(failure)}
        </p>
      ))}
      {/* Quiet whenever every provider searched for the title already shown
          above — only worth a line when one of them answered a different
          question than the user was told was asked. */}
      {substitutedQueries(found).map(([provider, query]) => (
        <p key={provider} className="font-mono text-label-sm text-outline">
          {providerName(provider)} searched for “{query}” instead.
        </p>
      ))}

      {found.candidates.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant">
          {found.errors.length > 0
            ? `Nothing found for “${found.query}” by the provider that answered.`
            : `No manga found for “${found.query}”. Both providers answered and neither had a match.`}
        </p>
      ) : (
        <>
          <p className="font-mono text-label-sm text-outline">
            {found.candidates.length} result{found.candidates.length === 1 ? '' : 's'} for “
            {found.query}”
          </p>
          <div className="grid grid-cols-1 gap-space-md xl:grid-cols-2">
            {found.candidates.map((candidate) => {
              const key = candidateKey(anime.id, candidate.provider, candidate.media_id)
              return (
                <SearchCandidateCard
                  key={key}
                  cardKey={key}
                  candidate={candidate}
                  choice={settingFor(key)}
                  busy={busy === key}
                  onStatus={(status) => onStatus(key, status)}
                  onDownload={(download) => onDownload(key, download)}
                  onAdd={() => onAdd(candidate)}
                />
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

import { useCallback } from 'react'

import { DetailPanel, ErrorState, Skeleton } from '../../ui'
import { api, type UnmatchedAnime } from '../../lib/api'
import { STATUS_LABEL, type ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import {
  discardedFormatPhrase,
  discardedRelationTitle,
  episodesCounted,
  providerName,
  relationPhrase,
  titleOf,
} from './labels'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function UnmatchedDetail({
  anime,
  onClose,
}: {
  anime: UnmatchedAnime
  onClose: () => void
}) {
  const load = useCallback(() => api.unmatchedDetail(anime.id), [anime.id])
  const { data, error, reload } = useAsyncData(load)

  return (
    <DetailPanel title={titleOf(anime)} onClose={onClose}>
      <div className="aspect-[2/3] w-32 overflow-hidden rounded-lg bg-surface-container-highest">
        {anime.cover_url && (
          <img src={anime.cover_url} alt="" className="h-full w-full object-cover" />
        )}
      </div>

      {/* The row already carried these, so they render before the request
          lands rather than sitting behind a skeleton the user does not need. */}
      <div className="flex flex-col gap-space-xs">
        {anime.title_romaji && <Row label="Romaji" value={anime.title_romaji} />}
        {anime.title_english && <Row label="English" value={anime.title_english} />}
        <Row
          label="Status"
          // UnmatchedAnime.status is typed as a plain string, but the backend
          // always serialises a ListStatus StrEnum member here (unmatched.py
          // converts every row's status through ListStatus(...) before it is
          // stored), so the cast is sound today. The fallback is what keeps it
          // honest rather than trusted: if a status the map does not cover
          // ever reached here, it would still render as-is instead of "undefined".
          value={STATUS_LABEL[anime.status as ListStatus] ?? anime.status.replace('_', ' ')}
        />
        {/* Same rule as the row behind this panel: a counter at zero beside
            a status of completed is MyAnimeList's two fields disagreeing, not
            a fact about the anime. */}
        {episodesCounted(anime) ? (
          <Row
            label="Episodes"
            value={
              anime.total_episodes != null
                ? `${anime.progress_episode} of ${anime.total_episodes}`
                : `${anime.progress_episode} watched`
            }
          />
        ) : (
          anime.total_episodes != null && (
            <Row label="Episodes" value={String(anime.total_episodes)} />
          )
        )}
      </div>

      {!data && error ? (
        <ErrorState title="Couldn't load the details" detail={error} onRetry={reload} />
      ) : !data ? (
        <div className="flex flex-col gap-space-sm">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <>
          {data.synonyms.length > 0 && (
            <section className="flex flex-col gap-space-xs">
              <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
                Also known as
              </h3>
              <div className="flex flex-wrap gap-space-sm">
                {data.synonyms.map((name) => (
                  <span
                    key={name}
                    className="rounded-full bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm text-on-surface-variant"
                  >
                    {name}
                  </span>
                ))}
              </div>
              {/* Every one of these is searched, which is why a filter that
                  matches none of the two titles above can still find this anime. */}
              <p className="text-body-sm text-outline">
                Every spelling is searched, not just the two titles above.
              </p>
            </section>
          )}

          <section className="flex flex-col gap-space-xs">
            <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
              On your lists
            </h3>
            {data.members.map((member) => (
              <div
                key={`${member.provider}:${member.media_id}`}
                className="flex items-center justify-between gap-space-sm"
              >
                <span className="text-body-sm text-on-surface">
                  {providerName(member.provider)}
                </span>
                {member.url ? (
                  <a
                    href={member.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-label-sm text-primary hover:underline"
                  >
                    #{member.media_id}
                  </a>
                ) : (
                  <span className="font-mono text-label-sm text-outline">
                    #{member.media_id}
                  </span>
                )}
              </div>
            ))}
          </section>

          {data.discarded_relations === null ? (
            // Recording fills forward from the next ANIME_LIST_SYNC. NULL means
            // this anime predates that, not that AniList declared nothing — the
            // one claim this panel must never make without having checked.
            <p className="text-body-sm text-on-surface-variant">
              This anime has not been through a sync that records why no manga was
              found for it. That will show here after the next anime sync.
            </p>
          ) : data.discarded_relations.length === 0 ? (
            <p className="text-body-sm text-on-surface-variant">
              Neither provider declared a manga for this anime. Searching by name is the
              only way to find one.
            </p>
          ) : (
            <section className="flex flex-col gap-space-xs">
              <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
                Why nothing matched
              </h3>
              <div className="flex flex-col gap-space-xs">
                {data.discarded_relations.map((relation) => (
                  <p
                    key={`${relation.provider}:${relation.media_id}:${relation.relation}`}
                    className="text-body-sm text-on-surface-variant"
                  >
                    AniList declared {relationPhrase(relation.relation)}, and it is{' '}
                    {discardedFormatPhrase(relation.format)}: {discardedRelationTitle(relation)}.
                  </p>
                ))}
              </div>
              <p className="text-body-sm text-outline">
                The downloader can only fetch manga, manhwa, manhua or OEL chapters.
              </p>
            </section>
          )}
        </>
      )}
    </DetailPanel>
  )
}

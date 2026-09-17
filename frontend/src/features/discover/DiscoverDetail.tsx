import { useCallback, useEffect, useState } from 'react'

import { AddToList, Button, CandidateList, DetailPanel, Skeleton, type SourceChoice } from '../../ui'
import { api, type DiscoverItem, type SearchCandidate } from '../../lib/api'
import { DEFAULT_STATUS, type ListStatus } from '../../lib/format'
import { KIND_LABEL } from './labels'

/**
 * What an item needs, asked for in the order it is owed.
 *
 * One panel rather than three, because the steps are the same steps: which
 * manga this is, what status it takes, and which source to read it from. Which
 * of them appear depends only on what the item still owes - never on which of
 * the three queues it arrived from. Keyed on the kind instead, a need with no
 * matching branch rendered nothing at all, and a card asking for a step the
 * panel would not offer is how that looked from the outside.
 *
 * Two of the three kinds need something the feed does not carry. A review item
 * has a candidate count but not the candidates, and an unmatched anime has none
 * at all until a search finds some - so both are fetched here, when the panel
 * opens, rather than loaded for every row in a list of hundreds.
 */
export function DiscoverDetail({
  item,
  onDone,
  onDismiss,
  onClose,
}: {
  item: DiscoverItem
  onDone: () => void
  onDismiss: () => void
  onClose: () => void
}) {
  const [status, setStatus] = useState<ListStatus>(DEFAULT_STATUS)
  const [download, setDownload] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [sources, setSources] = useState<SourceChoice[] | null>(null)
  // The source to confirm once the series exists. A suggestion has no series
  // yet, so the choice has to wait for the add rather than being made against
  // an id that is not there.
  const [source, setSource] = useState<string | null>(null)
  const [found, setFound] = useState<SearchCandidate[] | null>(null)
  const [picked, setPicked] = useState<SearchCandidate | null>(null)

  const needs = new Set(item.needs)

  // A review item's candidates live behind their own request. Fetched when the
  // panel opens so the list of hundreds does not pay for them.
  useEffect(() => {
    if (!needs.has('source') || item.series_id === null) return
    let current = true
    api
      .candidates(item.series_id)
      .then((payload) => {
        if (current) {
          setSources(
            payload.candidates.map((c) => ({
              url: c.source_url,
              site: c.source_site,
              score: c.score,
              title: c.title,
              cover_url: c.cover_url,
              chapters: c.chapter_count,
              year: c.year,
            })),
          )
        }
      })
      .catch((error: unknown) => current && setFailure(String(error)))
    return () => {
      current = false
    }
    // `needs` is rebuilt every render; the item's own identity is what decides
    // whether this should run again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.kind, item.id, item.series_id])

  const act = useCallback(async (run: () => Promise<unknown>) => {
    setBusy(true)
    setFailure(null)
    try {
      await run()
    } catch (error) {
      setFailure(String(error))
    } finally {
      setBusy(false)
    }
  }, [])

  const search = () =>
    void act(async () => {
      const result = await api.searchUnmatched(item.id)
      setFound(result.candidates)
      setPicked(null)
    })

  const addSuggestion = () =>
    void act(async () => {
      const added = await api.addSuggestion(item.id, status, download)
      // Confirming is a second call because the add is what creates the series
      // this mapping belongs to. Adding without a pick still works: an exact
      // match maps itself, and anything softer comes back here needing one.
      if (source) await api.confirmMapping(added.series_id, source)
      onDone()
    })

  const addPicked = () =>
    void act(async () => {
      if (!picked) return
      await api.addUnmatched(item.id, picked, status, download)
      onDone()
    })

  const confirmSource = (url: string) =>
    void act(async () => {
      if (item.series_id === null) return
      await api.confirmMapping(item.series_id, url)
      onDone()
    })

  const candidates = sources ?? item.candidates

  return (
    <DetailPanel title={item.title} onClose={onClose}>
      <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
        {KIND_LABEL[item.kind]}
      </span>
      <p className="text-body-sm text-on-surface-variant">{item.why}</p>

      {failure && <p className="text-body-sm text-error">{failure}</p>}

      {needs.has('match') && (
        <div className="flex flex-col gap-space-sm">
          <Button variant="primary" icon="search" disabled={busy} onClick={search}>
            {busy ? 'Searching…' : found ? 'Search again' : 'Search for the manga'}
          </Button>
          {found?.length === 0 && (
            <p className="text-body-sm text-outline">
              Nothing came back. The manga may not exist under this title.
            </p>
          )}
          {/* Picked first, added second. The status this is filed under is a
              separate decision from which manga it is, and asking both at once
              meant every result carried a status nobody had chosen. */}
          {found?.map((candidate) => {
            const chosen = picked?.provider === candidate.provider && picked.media_id === candidate.media_id
            return (
              <Button
                key={`${candidate.provider}:${candidate.media_id}`}
                variant={chosen ? 'primary' : 'surface'}
                disabled={busy}
                onClick={() => setPicked(candidate)}
              >
                {candidate.title}
              </Button>
            )
          })}
        </div>
      )}

      {/* A suggestion carries the sources its search already found, and until
          now they were served, typed and never drawn — so the one thing a
          reader wanted to decide was the one thing the screen never offered.
          Picking is optional: unpicked, the add maps an exact match itself. */}
      {needs.has('status') && candidates.length > 0 && (
        <div className="flex flex-col gap-space-xs">
          <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
            Source {source ? '' : '(optional)'}
          </span>
          <CandidateList
            candidates={candidates}
            chosen={source}
            busy={busy}
            onChoose={(candidate) => setSource(source === candidate.url ? null : candidate.url)}
          />
        </div>
      )}

      {needs.has('status') && (
        <AddToList
          idPrefix={`discover-${item.kind}-${item.id}`}
          status={status}
          download={download}
          busy={busy}
          onStatus={setStatus}
          onDownload={setDownload}
          onAdd={addSuggestion}
        />
      )}

      {picked && (
        <AddToList
          idPrefix={`discover-${item.kind}-${item.id}-picked`}
          addLabel={`Add ${picked.title}`}
          status={status}
          download={download}
          busy={busy}
          onStatus={setStatus}
          onDownload={setDownload}
          onAdd={addPicked}
        />
      )}

      {needs.has('source') && (
        <div className="flex flex-col gap-space-sm">
          <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
            Sources found
          </span>
          {sources === null ? (
            <Skeleton className="h-12 w-full" />
          ) : candidates.length === 0 ? (
            <p className="text-body-sm text-outline">
              No source was found for this one. It needs a URL pasted by hand on the series page.
            </p>
          ) : (
            // The series already exists, so picking one confirms it outright.
            <CandidateList
              candidates={candidates}
              busy={busy}
              onChoose={(candidate) => confirmSource(candidate.url)}
            />
          )}
        </div>
      )}

      <Button variant="ghost" disabled={busy} onClick={onDismiss}>
        Don't suggest this again
      </Button>
    </DetailPanel>
  )
}

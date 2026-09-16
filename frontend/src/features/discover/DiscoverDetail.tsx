import { useCallback, useEffect, useState } from 'react'

import { AddToList, Button, DetailPanel, Skeleton } from '../../ui'
import { api, type DiscoverItem, type SearchCandidate } from '../../lib/api'
import { DEFAULT_STATUS, type ListStatus } from '../../lib/format'

/**
 * What an item needs, asked for in the order it is owed.
 *
 * One panel rather than three, because the steps are the same steps: which
 * manga this is, what status it takes, and which source to read it from. Which
 * of them appear depends only on what the item still owes.
 *
 * Two of the three kinds need something the feed does not carry. A review item
 * has a candidate count but not the candidates, and an unmatched anime has no
 * candidates at all until a search finds some - so both are fetched here, when
 * the panel opens, rather than loaded for every row in a list of hundreds.
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
  const [sources, setSources] = useState<{ url: string; site: string; score: number }[] | null>(
    null,
  )
  const [found, setFound] = useState<SearchCandidate[] | null>(null)

  const needs = new Set(item.needs)

  // A review item's candidates live behind their own request. Fetched when the
  // panel opens so the list of hundreds does not pay for them.
  useEffect(() => {
    if (item.kind !== 'review' || item.series_id === null) return
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
            })),
          )
        }
      })
      .catch((error: unknown) => current && setFailure(String(error)))
    return () => {
      current = false
    }
  }, [item.kind, item.series_id])

  const act = useCallback(async (run: () => Promise<unknown>) => {
    setBusy(true)
    setFailure(null)
    try {
      await run()
      return true
    } catch (error) {
      setFailure(String(error))
      return false
    } finally {
      setBusy(false)
    }
  }, [])

  const search = () =>
    void act(async () => {
      const result = await api.searchUnmatched(item.id)
      setFound(result.candidates)
    })

  const addSuggestion = () =>
    void act(async () => {
      await api.addSuggestion(item.id, status, download)
      onDone()
    })

  const addFound = (candidate: SearchCandidate) =>
    void act(async () => {
      await api.addUnmatched(item.id, candidate, status, download)
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
          {found?.map((candidate) => (
            <Button
              key={`${candidate.provider}:${candidate.media_id}`}
              variant="surface"
              disabled={busy}
              onClick={() => addFound(candidate)}
            >
              Add {candidate.title}
            </Button>
          ))}
        </div>
      )}

      {needs.has('status') && item.kind === 'suggestion' && (
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

      {needs.has('source') && item.kind === 'review' && (
        <div className="flex flex-col gap-space-sm">
          <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
            Sources found
          </span>
          {sources === null ? (
            <Skeleton className="h-9 w-full" />
          ) : candidates.length === 0 ? (
            <p className="text-body-sm text-outline">
              No source was found for this one. It needs a URL pasted by hand on the series page.
            </p>
          ) : (
            candidates.map((candidate) => (
              <Button
                key={candidate.url}
                variant="surface"
                disabled={busy}
                onClick={() => confirmSource(candidate.url)}
              >
                {candidate.site} · {Math.round(candidate.score * 100)}%
              </Button>
            ))
          )}
        </div>
      )}

      <Button variant="ghost" disabled={busy} onClick={onDismiss}>
        Don't suggest this again
      </Button>
    </DetailPanel>
  )
}

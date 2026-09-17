import { useCallback, useEffect, useState } from 'react'

import { Button, CandidateList, Card, Icon, Skeleton, type SourceChoice } from '../../ui'
import { api, messageOf } from '../../lib/api'
import { useJobEvents } from '../../lib/useEvents'
import { PROVIDER_LABEL } from '../../lib/format'

// Markup reference: the "Pipeline & Mapeamento" block in
// .redesign/detalhes_do_mang_gest_o_de_pipeline_sincronia_multi_destino/code.html.
// The reference shows a MangaDex UUID, a mirror list and a ComicInfo.xml
// verification badge — none of which the API returns (the mapping is one
// source_site/source_url pair, nothing else) — so this shows only that pair
// and the action that requests a new one.
export function MappingPanel({
  seriesId,
  mapping,
  onResearch,
  onRemap,
}: {
  seriesId: number
  mapping: { source_site: string; source_url: string } | null
  onResearch: () => Promise<unknown>
  /** Supersede the mapping with a URL typed by hand. */
  onRemap: (sourceUrl: string) => Promise<unknown>
}) {
  const [status, setStatus] = useState<'idle' | 'busy' | 'queued'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [candidates, setCandidates] = useState<SourceChoice[] | null>(null)

  const loadCandidates = useCallback(() => {
    api
      .candidates(seriesId)
      .then((payload) =>
        setCandidates(
          payload.candidates.map((c) => ({
            url: c.source_url,
            site: c.source_site,
            score: c.score,
            title: c.title,
            cover_url: c.cover_url,
            chapters: c.chapter_count,
            year: c.year,
          })),
        ),
      )
      .catch(() => setCandidates([]))
  }, [seriesId])

  useEffect(loadCandidates, [loadCandidates])

  // The search is a job, and the candidates land when it finishes. Without
  // this the reader queues a search, is told it is queued, and has to reload
  // the page to find out it found anything — which is exactly the complaint
  // the Review screen used to draw.
  useJobEvents((event) => {
    if (event.event !== 'job.progress') loadCandidates()
  })

  const save = async () => {
    if (draft === null) return
    const url = draft.trim()
    if (!url || url === mapping?.source_url) {
      setDraft(null)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onRemap(url)
      setDraft(null)
    } catch (err) {
      // The address stays in the box on a refusal. The API rejects a URL no
      // source owns, and retyping it from memory is the last thing someone
      // whose paste was just rejected wants to do.
      setError(messageOf(err))
    } finally {
      setSaving(false)
    }
  }

  /** Taking a candidate is the same act as pasting its address, so it takes
      the same path — one refusal message, one reload, one place to change. */
  const confirm = async (url: string) => {
    setSaving(true)
    setError(null)
    try {
      await onRemap(url)
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setSaving(false)
    }
  }

  const research = async () => {
    setStatus('busy')
    setError(null)
    try {
      await onResearch()
      setStatus('queued')
    } catch (err) {
      // Reverting the button label without saying why reads as broken, not
      // declined — the download-range form already surfaces its own
      // rejection text, and this control has to match it.
      setStatus('idle')
      setError(messageOf(err))
    }
  }

  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <div className="flex items-center gap-space-xs">
        <Icon name="link" className="h-4 w-4 text-primary" />
        <h2 className="text-title-md text-on-surface">Source mapping</h2>
      </div>
      {draft !== null ? (
        <div className="flex flex-col gap-space-xs">
          <label className="font-mono text-label-sm text-outline" htmlFor="mapping-url">
            Source URL
          </label>
          <input
            id="mapping-url"
            value={draft}
            autoFocus
            spellCheck={false}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void save()
              if (event.key === 'Escape') setDraft(null)
            }}
            placeholder="https://mangadex.org/title/..."
            className="w-full rounded-lg bg-surface-container-highest px-space-sm py-2 font-mono text-body-sm text-on-surface outline-none ring-1 ring-outline-variant/40 focus:ring-primary"
          />
          {/* Said before the button is pressed: this is not an edit to a label,
              it re-reads the chapter list from the new source. */}
          <p className="text-body-sm text-on-surface-variant">
            Confirming supersedes the current mapping and re-runs chapter discovery.
          </p>
          <div className="flex items-center gap-space-xs">
            <Button variant="primary" size="sm" disabled={saving} onClick={save}>
              {saving ? 'Confirming…' : 'Confirm'}
            </Button>
            <Button variant="surface" size="sm" disabled={saving} onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : mapping ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-label-sm text-outline">
            {PROVIDER_LABEL[mapping.source_site] ?? mapping.source_site}
          </span>
          <a
            href={mapping.source_url}
            target="_blank"
            rel="noreferrer"
            className="truncate text-body-sm text-primary hover:underline"
          >
            {mapping.source_url}
          </a>
        </div>
      ) : (
        <p className="text-body-sm text-on-surface-variant">
          No source mapped yet — downloads cannot start until one is confirmed.
        </p>
      )}

      {/* Shown whether or not a mapping exists: re-running the search on a
          mapped series is how a wrong mapping gets corrected, and parking the
          results somewhere the reader cannot see them is what made that
          impossible. */}
      {candidates === null ? (
        <Skeleton className="h-12 w-full" />
      ) : candidates.length > 0 ? (
        <div className="flex flex-col gap-space-xs">
          <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
            {mapping ? 'Other sources found' : 'Sources found'}
          </span>
          <CandidateList
            candidates={candidates.filter((c) => c.url !== mapping?.source_url)}
            busy={saving}
            onChoose={(candidate) => void confirm(candidate.url)}
          />
        </div>
      ) : null}
      {draft === null && (
        <div className="flex flex-wrap items-center gap-space-xs">
          <Button
            variant="surface"
            size="sm"
            icon="sync"
            disabled={status === 'busy'}
            onClick={research}
            className="w-fit"
          >
            {status === 'queued' ? 'Search queued' : mapping ? 'Re-run search' : 'Find a source'}
          </Button>
          {/* The search parks candidates and waits for a decision, which is the
              right default. This is the way out when no candidate is the right
              one and the reader already knows the address. */}
          <Button
            variant="surface"
            size="sm"
            icon="link"
            onClick={() => setDraft(mapping?.source_url ?? '')}
            className="w-fit"
          >
            {mapping ? 'Edit source' : 'Paste a URL'}
          </Button>
        </div>
      )}
      {error && <p className="font-mono text-label-sm text-error">{error}</p>}
    </Card>
  )
}

import { useEffect, useState } from 'react'

import { Button, NoticeBar } from '../../ui'
import type { SeriesMetadata } from '../../lib/api'
import { messageOf } from '../../lib/api'

const MAX_NOTE = 5000

export function NotesPanel({
  metadata,
  onSave,
}: {
  metadata: SeriesMetadata
  onSave: (notes: string, tags: string[]) => Promise<void>
}) {
  const [draft, setDraft] = useState(metadata.notes ?? '')
  const [saving, setSaving] = useState(false)
  const [outcome, setOutcome] = useState<{ text: string; tone: 'info' | 'error' } | null>(null)

  // A note that arrives from a later refresh replaces the draft only when the
  // user has not started editing — otherwise a background reload would delete
  // what they were halfway through typing.
  useEffect(() => {
    setDraft((current) => (current === '' ? metadata.notes ?? '' : current))
  }, [metadata.notes])

  const save = async () => {
    setSaving(true)
    setOutcome(null)
    try {
      await onSave(draft, metadata.user_tags)
      setOutcome({ text: 'Note queued for your reading lists.', tone: 'info' })
    } catch (failure) {
      setOutcome({ text: messageOf(failure), tone: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-space-md">
      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        <h2 className="text-headline-sm text-on-surface">Your note</h2>
        <span className="font-mono text-label-sm text-outline">
          Visible only to you · {draft.length} / {MAX_NOTE}
        </span>
      </div>

      <textarea
        value={draft}
        maxLength={MAX_NOTE}
        rows={6}
        onChange={(event) => setDraft(event.target.value)}
        aria-label="Your note on this series"
        className="w-full rounded-lg bg-surface-container-lowest p-space-md text-body-md text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
        placeholder="Kept on your own list entry, not on this server."
      />

      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        {/* Only MyAnimeList has free tags; AniList's customLists are named
            lists, not tags. The row is absent when nothing carries any. */}
        {metadata.user_tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {metadata.user_tags.map((tag) => (
              <span
                key={tag}
                className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-on-surface-variant"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}
        <Button
          variant="primary"
          icon="save"
          disabled={saving || draft === (metadata.notes ?? '')}
          onClick={() => void save()}
        >
          {saving ? 'Saving…' : 'Save note'}
        </Button>
      </div>

      {outcome && <NoticeBar tone={outcome.tone} text={outcome.text} />}
    </div>
  )
}

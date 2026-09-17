import { useEffect, useState } from 'react'

import { Icon } from '../../ui'
import { STATUS_LABEL } from '../../lib/format'
import type { ListStatus } from '../../lib/format'
import { api } from '../../lib/api'

const CHOICES: ListStatus[] = ['reading', 'plan_to_read', 'on_hold', 'completed']

const DESTINATION_LABEL: Record<string, string> = {
  mal: 'MyAnimeList',
  anilist: 'AniList',
  mangabaka: 'MangaBaka',
  komga: 'Komga',
}

/**
 * The bar that acts on a selection, fixed to the bottom while one exists.
 *
 * The destinations are read from the API rather than written here. The obvious
 * hardcoding is already wrong — there is no MangaDex list provider, and which
 * providers accept a write changes as they gain write paths — and a bar
 * claiming a change reached a service it never touched is worse than a bar that
 * says nothing.
 */
export function BatchActionBar({
  count,
  busy,
  onApply,
  onRemove,
  onCancel,
}: {
  count: number
  busy: boolean
  onApply: (status: ListStatus) => Promise<void>
  /** Opens the confirmation. The bar states the intent; the page owns the
      question and the call, because destroying things is not a bar's job. */
  onRemove: () => void
  onCancel: () => void
}) {
  // No default. The design pre-selects one, but a bar that arrives with a
  // status already chosen turns a single mis-click into a status nobody picked,
  // written to every selected title and to their real accounts. Apply stays
  // disabled until the choice is made.
  const [status, setStatus] = useState<ListStatus | null>(null)
  const [destinations, setDestinations] = useState<string[]>([])

  useEffect(() => {
    let live = true
    api
      .statusDestinations()
      .then((body) => {
        if (live) setDestinations(body.destinations)
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [])

  const named = destinations.map((key) => DESTINATION_LABEL[key] ?? key).join(' · ')

  return (
    // Sticky rather than fixed. Pinned above the fold it looks the same, but a
    // fixed bar is outside the flow, so at the foot of the library it sat on
    // top of the last row of covers and there was no way to scroll them clear.
    // Sticky keeps its box in the layout: the page ends far enough down for the
    // last row to clear the bar, at any width and however tall the bar wraps.
    <div className="sticky bottom-8 z-50 mx-auto w-[95%] max-w-5xl">
      <div className="flex flex-col items-center justify-between gap-4 rounded-2xl border border-violet-500/40 bg-surface-container-lowest/95 p-3 shadow-batch-bar backdrop-blur-2xl transition-all sm:p-4 lg:flex-row">
        <div className="flex w-full flex-wrap items-center gap-3 lg:w-auto">
          <div className="flex items-center gap-2 rounded-xl border border-violet-500/30 bg-violet-500/20 px-3 py-1.5">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-violet-400" />
            <span
              className="font-mono text-label-sm font-bold text-violet-200"
              aria-live="polite"
            >
              {count} {count === 1 ? 'title selected' : 'titles selected'}
            </span>
          </div>

          <div className="flex flex-col font-mono text-label-sm leading-tight">
            {named && (
              <span className="flex items-center gap-1.5 text-on-surface">
                <span className="text-outline">Writes to:</span>
                <span className="font-semibold text-secondary">{named}</span>
              </span>
            )}
            {/* The reassurance worth giving before applying to thirty titles at
                once, and a real guarantee: a status write never carries
                progress. */}
            <span className="text-outline/70">Status only — your read chapters are untouched.</span>
          </div>
        </div>

        <div className="flex w-full flex-wrap items-center justify-between gap-3 lg:w-auto lg:justify-end">
          <div
            className="flex items-center gap-1 rounded-xl border border-outline-variant/30 bg-surface-container-high p-1"
            role="radiogroup"
            aria-label="Status to apply"
          >
            <span className="hidden px-2 font-mono text-label-sm text-outline xl:inline">Status:</span>
            {CHOICES.map((choice) => {
              const active = choice === status
              return (
                <button
                  key={choice}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setStatus(choice)}
                  className={
                    active
                      ? 'rounded-lg bg-violet-600 px-2.5 py-1 text-label-sm font-semibold text-white shadow-sm'
                      : 'rounded-lg px-2.5 py-1 text-label-sm text-on-surface-variant transition-colors hover:text-on-surface'
                  }
                >
                  {STATUS_LABEL[choice]}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy || status === null}
              onClick={() => status && onApply(status)}
              className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-primary px-4 py-2 font-title-md text-label-sm font-bold text-on-primary shadow-lg shadow-violet-600/30 transition-all hover:shadow-violet-600/50 hover:brightness-110 active:scale-95 disabled:opacity-60"
            >
              <Icon name="bolt" className="text-[1rem]" />
              <span>
                {busy ? 'Queueing…' : status ? `Apply & sync (${count})` : 'Pick a status'}
              </span>
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onRemove}
              className="rounded-xl bg-surface-container px-3 py-2 font-mono text-label-sm text-error transition-colors hover:bg-error/[0.12] disabled:opacity-60"
            >
              Remove
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="rounded-xl bg-surface-container px-3 py-2 font-mono text-label-sm text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

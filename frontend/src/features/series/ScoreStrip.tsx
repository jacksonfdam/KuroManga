import { Card } from '../../ui'
import type { SeriesMetadata } from '../../lib/api'

/** "54,291" — thousands separated, because a six-figure vote count run
 * together is unreadable at label size. */
function grouped(value: number): string {
  return value.toLocaleString('en-GB')
}

function Cell({
  label,
  value,
  detail,
  tone = 'text-on-surface',
}: {
  label: string
  value: string
  detail?: string | null
  tone?: string
}) {
  return (
    <div className="flex flex-col gap-space-xs">
      <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
        {label}
      </span>
      <span className={`text-headline-md ${tone}`}>{value}</span>
      {detail && <span className="font-mono text-label-sm text-outline">{detail}</span>}
    </div>
  )
}

/**
 * The mockup's four-cell strip: global score, personal rating, cadence and
 * ranking. Cadence is dropped — neither provider reports a manga's release
 * schedule, and it would be the one invented figure on the screen. Volumes
 * take the empty cell, and they are served.
 *
 * A cell whose value no provider returned is not rendered. The strip disappears
 * entirely when none of the four is known.
 */
export function ScoreStrip({ metadata }: { metadata: SeriesMetadata }) {
  const cells = [
    metadata.global_score != null && (
      <Cell
        key="global"
        label="Global score"
        value={`★ ${metadata.global_score.toFixed(1)}`}
        detail={metadata.vote_count != null ? `${grouped(metadata.vote_count)} votes` : null}
        tone="text-tertiary"
      />
    ),
    metadata.user_score != null && (
      <Cell key="mine" label="My rating" value={`${metadata.user_score.toFixed(1)} / 10`} />
    ),
    metadata.volumes_total != null && (
      <Cell
        key="volumes"
        label="Volumes"
        // volumes_read is nullable independently of the total: a provider can
        // report how many volumes exist without reporting how many were read.
        // "0 / 18 read" would assert a count nobody gave.
        value={
          metadata.volumes_read != null
            ? `${metadata.volumes_read} / ${metadata.volumes_total}`
            : `${metadata.volumes_total}`
        }
        detail={metadata.volumes_read != null ? 'read' : 'in total'}
      />
    ),
    metadata.rank != null && (
      <Cell key="rank" label="Overall ranking" value={`#${metadata.rank}`} />
    ),
  ].filter(Boolean)

  if (cells.length === 0) return null

  return (
    <Card as="section" elevated className="grid grid-cols-2 gap-space-lg md:grid-cols-4">
      {cells}
    </Card>
  )
}

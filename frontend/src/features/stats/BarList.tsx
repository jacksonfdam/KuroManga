import { ProgressBar } from '../../ui'
import { grouped } from './labels'

type Tone = 'primary' | 'secondary' | 'tertiary' | 'warning' | 'error'

export interface BarRow {
  key: string
  label: string
  value: number
  /** A second figure about the same row — a share of the whole, never a
      different quantity dressed as one. */
  detail?: string
  tone?: Tone
}

/**
 * A ranked list where each row carries its own bar, composed from the
 * ProgressBar the rest of the interface already uses. No charting library is
 * involved: every bar here is one number against the largest of its siblings,
 * which is a division and a width.
 */
export function BarList({ rows }: { rows: BarRow[] }) {
  // Scaled against the largest row rather than against the total: ten genres
  // sharing one shelf would otherwise all draw as slivers of the same width.
  const max = rows.reduce((high, row) => Math.max(high, row.value), 0)

  return (
    <ul className="flex flex-col gap-space-md">
      {rows.map((row) => (
        <li key={row.key} className="flex flex-col gap-space-xs">
          <div className="flex items-baseline justify-between gap-space-sm">
            <span className="truncate text-body-md text-on-surface">{row.label}</span>
            <span className="shrink-0 font-mono text-label-md text-on-surface-variant">
              {grouped(row.value)}
              {row.detail && <span className="text-outline"> · {row.detail}</span>}
            </span>
          </div>
          <ProgressBar value={row.value} max={max} tone={row.tone ?? 'primary'} />
        </li>
      ))}
    </ul>
  )
}

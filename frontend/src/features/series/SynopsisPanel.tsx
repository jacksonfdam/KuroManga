import { Card } from '../../ui'
import type { SeriesMetadata } from '../../lib/api'

/**
 * AniList returns its description with `<br>` and `<i>` in it. Rendering it as
 * markup would mean trusting a third party's sanitiser with our DOM, so the
 * tags are stripped and the paragraphs are split on the breaks they marked.
 */
function paragraphs(synopsis: string): string[] {
  return synopsis
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .split(/\n{2,}|\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function SynopsisPanel({ metadata }: { metadata: SeriesMetadata }) {
  const rows = [
    metadata.native_title && { label: 'Original title', value: metadata.native_title },
    metadata.publisher && { label: 'Magazine', value: metadata.publisher },
    metadata.country && { label: 'Country of origin', value: metadata.country },
    metadata.demographic && { label: 'Demographic', value: metadata.demographic },
    metadata.popularity != null && {
      label: 'On lists',
      value: metadata.popularity.toLocaleString('en-GB'),
    },
  ].filter(Boolean) as { label: string; value: string }[]

  if (!metadata.synopsis && rows.length === 0) return null

  return (
    <Card as="section" elevated className="flex flex-col gap-space-md">
      <h2 className="text-headline-sm text-on-surface">Synopsis</h2>
      {metadata.synopsis ? (
        <div className="flex flex-col gap-space-sm">
          {paragraphs(metadata.synopsis).map((line, index) => (
            <p key={index} className="text-body-md text-on-surface-variant">
              {line}
            </p>
          ))}
        </div>
      ) : (
        <p className="text-body-sm text-outline">No provider returned a synopsis.</p>
      )}
      {rows.length > 0 && (
        <div className="flex flex-col gap-space-xs border-t border-outline-variant pt-space-md">
          {rows.map((row) => (
            <Row key={row.label} label={row.label} value={row.value} />
          ))}
        </div>
      )}
    </Card>
  )
}

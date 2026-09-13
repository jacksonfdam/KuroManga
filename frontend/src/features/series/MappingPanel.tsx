import { useState } from 'react'

import { Button, Card, Icon } from '../../ui'
import { PROVIDER_LABEL } from '../../lib/format'

// Markup reference: the "Pipeline & Mapeamento" block in
// .redesign/detalhes_do_mang_gest_o_de_pipeline_sincronia_multi_destino/code.html.
// The reference shows a MangaDex UUID, a mirror list and a ComicInfo.xml
// verification badge — none of which the API returns (the mapping is one
// source_site/source_url pair, nothing else) — so this shows only that pair
// and the action that requests a new one.
export function MappingPanel({
  mapping,
  onResearch,
}: {
  mapping: { source_site: string; source_url: string } | null
  onResearch: () => Promise<unknown>
}) {
  const [status, setStatus] = useState<'idle' | 'busy' | 'queued'>('idle')
  const [error, setError] = useState<string | null>(null)

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
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <div className="flex items-center gap-space-xs">
        <Icon name="link" className="h-4 w-4 text-primary" />
        <h2 className="text-title-md text-on-surface">Source mapping</h2>
      </div>
      {mapping ? (
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
          No source mapped yet — downloads cannot start until one is confirmed in Review.
        </p>
      )}
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
      {error && <p className="font-mono text-label-sm text-error">{error}</p>}
    </Card>
  )
}

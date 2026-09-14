import type { ReactNode } from 'react'

import { Card, Icon, type IconName } from '../../ui'

// Shell taken from the MangaDex / Comick cards in
// .redesign/ajustes_configura_es_do_homelab_integra_es/code.html. The mockup's
// per-source ping latency, request rate and "Ver Logs do Container" link are
// dropped — none of that is data the API serves, and MangaDex/Comick each get
// their own facts and controls passed in as children instead of a shared shape
// that would have to fabricate one side to fit the other.
const DOT: Record<'ok' | 'neutral' | 'warning', string> = {
  ok: 'bg-secondary',
  neutral: 'bg-outline',
  warning: 'bg-warning',
}

export function SourceCard({
  icon,
  title,
  subtitle,
  tone,
  statusLabel,
  children,
}: {
  icon: IconName
  title: string
  subtitle: string
  tone: 'ok' | 'neutral' | 'warning'
  statusLabel: string
  children: ReactNode
}) {
  return (
    <Card elevated className="flex flex-col gap-space-md">
      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        <div className="flex items-center gap-space-sm">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-container/[0.2] text-primary">
            <Icon name={icon} />
          </div>
          <div>
            <h3 className="text-title-md text-on-surface">{title}</h3>
            <span className="font-mono text-label-sm text-on-surface-variant">{subtitle}</span>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-container-high px-space-sm py-1 font-mono text-label-sm text-on-surface-variant">
          <span className={`h-1.5 w-1.5 rounded-full ${DOT[tone]}`} />
          {statusLabel}
        </span>
      </div>
      {children}
    </Card>
  )
}

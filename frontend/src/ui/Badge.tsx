import type { ReactNode } from 'react'

// Markup taken from the nav item counters (e.g. "Revisão 12") in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
// Solid *-container fill, unlike StatusPill's 12%-tint — the two pill styles
// mean two different things and should not look alike.
const TONE: Record<string, string> = {
  primary: 'bg-primary-container text-on-primary-container',
  secondary: 'bg-secondary-container text-on-secondary-container',
  tertiary: 'bg-tertiary-container text-on-tertiary-container',
  warning: 'bg-warning-container text-on-warning-container',
  error: 'bg-error-container text-on-error-container',
}

export function Badge({
  tone = 'secondary',
  children,
}: {
  tone?: 'primary' | 'secondary' | 'tertiary' | 'warning' | 'error'
  children: ReactNode
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-space-xs py-0.5 font-mono text-label-sm font-semibold ${TONE[tone]}`}
    >
      {children}
    </span>
  )
}

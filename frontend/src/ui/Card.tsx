import type { ElementType, ReactNode } from 'react'

// Markup taken from the metrics bento cards in
// .redesign/home_dashboard_de_entrada_controle_homelab/code.html and the
// integration cards in .redesign/ajustes_configura_es_do_homelab_integra_es/code.html.
export function Card({
  as = 'div',
  elevated = false,
  className = '',
  children,
}: {
  as?: 'div' | 'section'
  elevated?: boolean
  className?: string
  children: ReactNode
}) {
  const As = as as ElementType
  return (
    <As className={`rounded-xl bg-surface-container p-space-lg ${elevated ? 'shadow-card' : 'shadow-sm'} ${className}`}>
      {children}
    </As>
  )
}

import type { ReactNode } from 'react'

// Markup taken from the status-filter tabs ("Lendo 14", "Planejados 28", ...)
// in .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
export function Chip({
  active,
  count,
  onClick,
  children,
}: {
  active: boolean
  count?: number
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      // font-title-md generates no rule (title-md is a fontSize key, not a
      // fontFamily one) — font-semibold is the weight it was standing in for.
      className={`flex shrink-0 items-center gap-space-xs rounded-xl px-space-md py-space-sm text-body-sm font-semibold transition-all ${
        active
          ? 'bg-primary text-on-primary shadow-sm'
          : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
      }`}
    >
      <span>{children}</span>
      {count !== undefined && (
        <span
          className={`rounded-full px-space-sm py-0.5 font-mono text-label-sm ${
            active ? 'bg-on-primary/20 text-on-primary' : 'bg-surface-container text-outline'
          }`}
        >
          {count}
        </span>
      )}
    </button>
  )
}

import type { ButtonHTMLAttributes } from 'react'

import { Icon, type IconName } from './Icon'

// Markup taken from the "Dispensar sugestão" dismiss control in
// .redesign/home_dashboard_de_entrada_controle_homelab/code.html.
interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName
  label: string
}

export function IconButton({ icon, label, className = '', ...rest }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      title={label}
      className={`inline-flex items-center justify-center rounded-lg bg-surface-container-highest p-space-xs text-outline transition-colors hover:bg-surface-bright hover:text-on-surface disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...rest}
    >
      <Icon name={icon} />
    </button>
  )
}

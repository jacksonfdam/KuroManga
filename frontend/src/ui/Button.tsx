import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { Icon, type IconName } from './Icon'

// Markup taken from the "Forçar Varredura" / "Explorar Descobertas" quick action
// buttons in .redesign/home_dashboard_de_entrada_controle_homelab/code.html.
const VARIANT: Record<string, string> = {
  primary: 'bg-primary text-on-primary hover:bg-primary-container',
  surface: 'bg-surface-container-high text-on-surface shadow-sm hover:bg-surface-bright',
  ghost: 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface',
}

// text-label-md already carries both size and weight (tailwind.config.ts defines
// label-md only under fontSize, not fontFamily) — a paired font-label-md class
// generates no rule and is dead weight.
const SIZE: Record<string, string> = {
  sm: 'px-space-sm py-space-xs text-label-md',
  md: 'px-space-md py-space-sm text-label-md',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'surface' | 'ghost'
  size?: 'sm' | 'md'
  icon?: IconName
  children: ReactNode
}

export function Button({
  variant = 'surface',
  size = 'md',
  icon,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center gap-space-xs rounded-lg transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${SIZE[size]} ${className}`}
      {...rest}
    >
      {icon && <Icon name={icon} />}
      {children}
    </button>
  )
}

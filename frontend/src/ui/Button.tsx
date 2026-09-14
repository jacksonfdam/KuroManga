import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { Icon, type IconName } from './Icon'

// Markup taken from the "Forçar Varredura" / "Explorar Descobertas" quick action
// buttons in .redesign/home_dashboard_de_entrada_controle_homelab/code.html.
const VARIANT: Record<string, string> = {
  primary: 'bg-primary text-on-primary hover:bg-primary-container',
  surface: 'bg-surface-container-high text-on-surface shadow-sm hover:bg-surface-bright',
  ghost: 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface',
  // The 12%-tint-over-solid pairing StatusPill already uses for a state that
  // needs to read as a warning rather than a neutral action.
  danger: 'bg-error/[0.12] text-error hover:bg-error-container hover:text-on-error-container',
}

// text-label-md already carries both size and weight (tailwind.config.ts defines
// label-md only under fontSize, not fontFamily) — a paired font-label-md class
// generates no rule and is dead weight.
const SIZE: Record<string, string> = {
  sm: 'px-space-sm py-space-xs text-label-md',
  md: 'px-space-md py-space-sm text-label-md',
}

/**
 * The button's own classes, without the button.
 *
 * Home's "Review mappings" and "Explore discovery" navigate, so they are
 * anchors and not buttons — but they are the same control to look at, and a
 * second copy of this class list is how two controls that should match stop
 * matching. `ui/` stays free of the router; the caller renders the element.
 */
export function buttonClass({
  variant = 'surface',
  size = 'md',
  className = '',
}: {
  variant?: 'primary' | 'surface' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  className?: string
} = {}): string {
  return `inline-flex items-center gap-space-xs rounded-lg transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${SIZE[size]} ${className}`
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'surface' | 'ghost' | 'danger'
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
    <button className={buttonClass({ variant, size, className })} {...rest}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  )
}

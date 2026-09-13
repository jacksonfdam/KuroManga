const ICONS = {
  sync: 'M12 4V1L8 5l4 4V6a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8z',
  add: 'M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z',
  check: 'M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z',
  grid: 'M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z',
  list: 'M3 5h18v2H3zm0 6h18v2H3zm0 6h18v2H3z',
  search: 'M15.5 14h-.8l-.3-.3a6.5 6.5 0 1 0-.7.7l.3.3v.8l5 5 1.5-1.5zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z',
  book: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm0 18H6V4h12z',
  download: 'M12 16 7 11l1.4-1.4L11 12.2V4h2v8.2l2.6-2.6L17 11zM5 18h14v2H5z',
  settings: 'M12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5zm7.4-2.3.1-1.2-.1-1.2 2-1.5-2-3.4-2.3 1a7.6 7.6 0 0 0-2-1.2l-.4-2.4h-4l-.4 2.4a7.6 7.6 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5-.1 1.2.1 1.2-2 1.5 2 3.4 2.3-1a7.6 7.6 0 0 0 2 1.2l.4 2.4h4l.4-2.4a7.6 7.6 0 0 0 2-1.2l2.3 1 2-3.4z',
  sparkle: 'M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z',
  chart: 'M4 20V10h4v10zm6 0V4h4v16zm6 0v-6h4v6z',
  warning: 'M1 21h22L12 2zm12-3h-2v-2h2zm0-4h-2v-4h2z',
  chevron: 'M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z',
} as const

export type IconName = keyof typeof ICONS

export function Icon({ name, className = 'h-4 w-4' }: { name: IconName; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d={ICONS[name]} />
    </svg>
  )
}

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
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  server: 'M4 4h16v4H4V4zm0 6h16v4H4v-4zm0 6h16v4H4v-4zm2-10.5h2v1.5H6V5.5zm0 6h2v1.5H6V11.5zm0 6h2v1.5H6v-1.5z',
  save: 'M17 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7l-4-4zm-5 16a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm3-10H6V5h9v4z',
  folder: 'M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2z',
  bolt: 'M11 21v-7H7l6-11v7h4z',
  check_box: 'M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-9 14-4-4 1.4-1.4L10 14.2l6.6-6.6L18 9z',
  lock: 'M12 1a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1V6a5 5 0 0 0-5-5zm-3 5a3 3 0 0 1 6 0v3H9V6zm3 8a2 2 0 1 1 0 4 2 2 0 0 1 0-4z',
} as const

export type IconName = keyof typeof ICONS

export function Icon({ name, className = 'h-4 w-4' }: { name: IconName; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d={ICONS[name]} />
    </svg>
  )
}

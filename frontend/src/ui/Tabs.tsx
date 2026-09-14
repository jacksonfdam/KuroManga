// The tab strip over "Capítulos & Histórico (172) / Minhas Notas / Personagens"
// in the detail mockup. It lives in ui/ rather than the series folder because
// the unmatched detail panel wants the same strip, and feature folders never
// import from each other.
export function Tabs<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number | null }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div
      role="tablist"
      className="flex flex-wrap items-center gap-space-xs border-b border-outline-variant"
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(option.value)}
            className={`-mb-px rounded-t-lg border-b-2 px-space-md py-space-sm text-label-md transition-colors ${
              selected
                ? 'border-primary text-on-surface'
                : 'border-transparent text-outline hover:text-on-surface'
            }`}
          >
            {option.label}
            {/* A count only when the API served one. A tab reading "(0)" where
                the number is simply unknown is the invented-figure problem in
                miniature. */}
            {option.count != null && (
              <span className="ml-space-xs font-mono text-label-sm text-outline">
                ({option.count})
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

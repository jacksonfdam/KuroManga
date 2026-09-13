import { Icon, type IconName } from './Icon'

// Markup taken from the Grade/Tabela view switcher in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; icon?: IconName; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    // DESIGN.md's View Switcher spec calls for a 1px container border; the
    // hairline value is the same one used for card perimeters elsewhere.
    <div className="inline-flex items-center gap-1 rounded-xl border border-white/[0.08] bg-surface-container-lowest p-1 shadow-inner">
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-pressed={selected}
            // The label collapses to an icon-only button below sm (hidden, not just
            // visually clipped, so it drops out of the accessibility tree too) —
            // aria-label keeps the button nameable at every width.
            aria-label={option.label}
            className={`flex items-center gap-space-xs rounded-lg px-space-md py-space-sm text-body-sm font-semibold transition-all ${
              selected
                ? 'bg-surface-container-highest text-on-surface'
                : 'text-outline hover:text-on-surface'
            }`}
          >
            {option.icon && <Icon name={option.icon} />}
            {/* text-label-md carries size and weight on its own (label-md has no
                matching fontFamily entry — font-label-md generated no rule). */}
            <span className="hidden text-label-md sm:inline">{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}

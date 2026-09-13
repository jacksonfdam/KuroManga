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
    <div className="inline-flex items-center gap-1 rounded-xl bg-surface-container-lowest p-1 shadow-inner">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`flex items-center gap-space-xs rounded-lg px-space-md py-space-sm text-body-sm font-semibold transition-all ${
            option.value === value
              ? 'bg-surface-container-highest text-on-surface'
              : 'text-outline hover:text-on-surface'
          }`}
        >
          {option.icon && <Icon name={option.icon} />}
          <span className="hidden font-label-md text-label-md sm:inline">{option.label}</span>
        </button>
      ))}
    </div>
  )
}

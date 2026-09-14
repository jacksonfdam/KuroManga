// Markup taken from the automation toggles in
// .redesign/ajustes_configura_es_do_homelab_integra_es/code.html.
export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  disabled?: boolean
}) {
  return (
    <label
      className={`inline-flex items-center gap-space-sm ${
        disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
      }`}
    >
      <span className="relative inline-flex h-6 w-11 shrink-0 items-center">
        <input
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="absolute inset-0 rounded-full bg-surface-variant transition-colors peer-checked:bg-secondary" />
        <span className="absolute left-1 h-4 w-4 rounded-full bg-on-surface transition-transform peer-checked:translate-x-5 peer-checked:bg-on-secondary-container" />
      </span>
      <span className="text-body-md text-on-surface">{label}</span>
    </label>
  )
}

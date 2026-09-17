import { Button } from './Button'
import { Icon } from './Icon'

/**
 * The controls a long list needs, in one place because two screens need them.
 *
 * The search field is the library's, lifted here unchanged rather than copied:
 * Discover asked for the same control and a second copy is how two boxes that
 * look alike stop behaving alike.
 */
export function SearchField({
  name,
  label,
  value,
  onChange,
  placeholder,
}: {
  name: string
  label: string
  value: string
  onChange: (value: string) => void
  placeholder: string
}) {
  return (
    <div className="relative w-full sm:w-72">
      <span className="pointer-events-none absolute left-3 top-2.5 text-outline">
        <Icon name="search" className="h-4 w-4" />
      </span>
      <input
        name={name}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg bg-surface-container-low py-2 pl-9 pr-4 text-body-sm text-on-surface placeholder:text-outline focus:bg-surface-container focus:outline-none"
      />
    </div>
  )
}

/** A labelled select. Native, because the platform's own list is reachable by
    keyboard and by screen reader without any of it being rebuilt here. */
export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <label className="flex items-center gap-space-xs">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
        className="rounded-lg bg-surface-container-low px-space-sm py-2 text-body-sm text-on-surface focus:bg-surface-container focus:outline-none"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

/**
 * Where you are in the list, and how to leave it.
 *
 * The page number is shown rather than only implied by the buttons, because it
 * is in the address: a reader who bookmarks page 7 should be able to see that
 * is where they are.
 */
export function Pager({
  page,
  pages,
  total,
  per,
  onPage,
}: {
  page: number
  pages: number
  total: number
  per: number
  onPage: (page: number) => void
}) {
  const first = total === 0 ? 0 : (page - 1) * per + 1
  const last = Math.min(page * per, total)
  return (
    <div className="flex flex-wrap items-center gap-space-md">
      <Button variant="surface" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <Button variant="surface" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </Button>
      <span className="font-mono text-label-sm text-outline">
        {first}–{last} of {total} · page {page} of {pages}
      </span>
    </div>
  )
}

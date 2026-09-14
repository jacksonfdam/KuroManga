import { Chip } from '../../ui'
import type { Series } from '../../lib/api'
import { STATUS_LABEL, STATUS_ORDER, type ListStatus } from '../../lib/format'


export function StatusTabs({
  all,
  status,
  onChange,
}: {
  all: Series[]
  status: ListStatus | 'all'
  onChange: (status: ListStatus | 'all') => void
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto py-0.5">
      {STATUS_ORDER.map((key) => (
        <Chip key={key} active={status === key} count={all.filter((row) => row.status === key).length} onClick={() => onChange(key)}>
          {STATUS_LABEL[key]}
        </Chip>
      ))}
      <Chip active={status === 'all'} count={all.length} onClick={() => onChange('all')}>
        All
      </Chip>
    </div>
  )
}

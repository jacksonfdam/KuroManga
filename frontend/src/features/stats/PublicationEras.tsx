import { Card } from '../../ui'
import type { Stats } from '../../lib/api'
import { Columns } from './Columns'
import { grouped } from './labels'

/**
 * When the shelf was published, by decade.
 *
 * The endpoint includes the empty decades between the populated ones, and
 * they are drawn: a decade dropped from the list would render as a narrower
 * bar beside its neighbour rather than as the gap it actually is.
 *
 * The count with no year is printed underneath, because a histogram built
 * from two thirds of a library must not present itself as the whole of one.
 */
export function PublicationEras({
  eras,
  withoutYear,
}: {
  eras: Stats['publication_eras']
  withoutYear: number
}) {
  const total = eras.reduce((sum, era) => sum + era.count, 0)

  return (
    <Card as="section" elevated>
      <h2 className="text-title-md text-on-surface">When it was published</h2>
      <p className="mt-space-xs text-body-sm text-on-surface-variant">
        Tracked series by the decade their publication started.
      </p>

      <div className="mt-space-lg">
        {eras.length === 0 ? (
          <p className="text-body-md text-on-surface-variant">
            {withoutYear > 0
              ? `No publication year is known for anything tracked — all ${grouped(withoutYear)} of them are missing one, so there is no era to plot.`
              : 'Nothing is tracked yet, so there is no publication history to plot.'}
          </p>
        ) : (
          <>
            <Columns
              tone="tertiary"
              label={`Tracked series by decade of first publication, ${eras
                .map((era) => `${era.label}: ${era.count}`)
                .join(', ')}.`}
              bars={eras.map((era) => ({
                key: String(era.decade),
                value: era.count,
                top: String(era.count),
                caption: era.label,
                title: `${era.label} · ${grouped(era.count)} series`,
              }))}
            />
            <p className="mt-space-md text-body-sm text-on-surface-variant">
              {withoutYear > 0
                ? `${grouped(withoutYear)} tracked ${withoutYear === 1 ? 'series carries' : 'series carry'} no publication year, so ${withoutYear === 1 ? 'it is' : 'they are'} in none of these columns — ${grouped(total)} of them are.`
                : `Every tracked series carries a publication year, so all ${grouped(total)} are counted here.`}
            </p>
          </>
        )}
      </div>
    </Card>
  )
}

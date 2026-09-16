import type { Location } from 'react-router-dom'

/**
 * Where a detail screen came from, and what to call it.
 *
 * The series screen used to render its back link as a hardcoded `/library`.
 * Reached from Discover or from Home — both of which link to a series — the
 * one control that means "go back" put the user on a screen they had not been
 * on, and the place they left was gone.
 *
 * The origin travels in the link's history state rather than in a query
 * parameter: it belongs to the act of navigating, not to the series being
 * shown, and two links to the same series from two screens should not be two
 * different addresses.
 */
export interface Origin {
  from: string
}

/** What a link into a detail screen should carry, so the way back is known. */
export function originState(location: Location): Origin {
  return { from: location.pathname + location.search }
}

const LABELS: Record<string, string> = {
  '/': 'home',
  '/stats': 'statistics',
  '/library': 'library',
  '/discover': 'discover',
  '/downloads': 'downloads',
}

/**
 * History state is not trustworthy input — it survives reloads, it can be
 * written by hand, and it is replayed from whatever a previous build put
 * there. So a `from` is used only when it is a path within this application:
 * it must begin with a single slash, which rules out both an absolute URL and
 * the `//host` form that a browser reads as protocol-relative and would follow
 * off-site.
 */
export function backTo(location: Location): { to: string; label: string } {
  const state = location.state as Origin | null
  const from = state?.from
  const usable = typeof from === 'string' && from.startsWith('/') && !from.startsWith('//')
  // The library is the fallback because it is the screen most series are
  // reached from, and it is the one place every series is listed.
  const to = usable ? from : '/library'
  const label = LABELS[to.split('?')[0]] ?? 'library'
  return { to, label }
}

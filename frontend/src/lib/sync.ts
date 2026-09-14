import { api, messageOf } from './api'

/**
 * The providers a scan actually reads.
 *
 * Named here rather than taken from the header's integration strip, because
 * that strip lists every integration and only the two list providers are
 * synced. The shell's "Sync all" and Home's "Force scan" are the same act, so
 * they must not disagree about which providers it covers.
 */
export const SYNCED: [string, string][] = [
  ['mal', 'MyAnimeList'],
  ['anilist', 'AniList'],
]

/**
 * Queue a list sync on every synced provider, and report the ones that
 * refused. An unauthenticated provider rejects, and firing both promises
 * without looking at either meant the click reported nothing at all —
 * allSettled so one dead provider does not hide the other one having worked.
 */
export async function syncLists(): Promise<string[]> {
  const results = await Promise.allSettled(SYNCED.map(([provider]) => api.sync(provider)))
  return results.flatMap((result, index) =>
    result.status === 'rejected' ? [`${SYNCED[index][1]}: ${messageOf(result.reason)}`] : [],
  )
}

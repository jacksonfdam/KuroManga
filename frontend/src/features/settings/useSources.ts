import { useCallback, useState } from 'react'

import { api, type Source } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useNotice } from '../../lib/useNotice'

/**
 * The catalogue as this screen drives it: one page at a time, filtered, with a
 * toggle per row.
 *
 * Paging is the API's, not this hook's. The catalogue is generated output and
 * grows to four figures, so the screen holds a page and asks for the next one
 * rather than holding the whole thing and slicing it.
 */
export function useSources() {
  const [query, setQuery] = useState('')
  const [lang, setLang] = useState('')
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState<string | null>(null)
  const { notice, report, reportFailure, clear } = useNotice()

  const load = useCallback(
    () => api.sources({ q: query || undefined, lang: lang || undefined, page }),
    [query, lang, page],
  )
  const { data, error, reload } = useAsyncData(load)

  const toggle = useCallback(
    async (source: Source) => {
      setBusy(source.key)
      clear()
      try {
        const updated = await api.setSourceEnabled(source.key, !source.enabled)
        report(
          updated.enabled
            ? `${updated.name} will be searched when a series needs matching.`
            : `${updated.name} will no longer be searched.`,
        )
        reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(null)
      }
    },
    [clear, reload, report, reportFailure],
  )

  // Searching or filtering returns to the first page. Page four of a narrowed
  // result is usually empty, and an empty page reads as "no site matches"
  // rather than "you are past the end of this one".
  const search = useCallback((value: string) => {
    setQuery(value)
    setPage(1)
  }, [])

  const filterLanguage = useCallback((value: string) => {
    setLang(value)
    setPage(1)
  }, [])

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    page: data?.page ?? 1,
    size: data?.size ?? 50,
    loaded: data !== null,
    error,
    reload,
    notice,
    busy,
    query,
    lang,
    search,
    filterLanguage,
    setPage,
    toggle,
  }
}

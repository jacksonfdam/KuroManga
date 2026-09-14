import { useCallback, useState } from 'react'

import { api } from './api'
import type { ListStatus } from './format'
import type { NoticeApi } from './useNotice'

/** Every field either screen needs to answer for a suggestion. */
export interface Approvable {
  id: number
  title: string
}

/**
 * Approving and dismissing a suggestion, once.
 *
 * Discovery renders the decision with a status picker and a download toggle;
 * Home renders it as a single click on a highlight. They are the same two
 * writes against the same two routes, and the sentence a user is shown after
 * an approval — in particular the one about a mapping that still needs
 * confirming — must not depend on which screen the click happened on. A
 * feature folder may not import another, so the shared half lives here.
 */
export function useSuggestionActions(notice: NoticeApi, onChanged: () => void) {
  const [busy, setBusy] = useState<number | null>(null)
  const { report, fail, reportFailure, clear } = notice

  const approve = useCallback(
    async (item: Approvable, status: ListStatus, download: boolean) => {
      setBusy(item.id)
      clear()
      try {
        const result = await api.addSuggestion(item.id, status, download)
        // The card goes away either way, so this is the only moment left to say
        // the mapping is pending: nothing downloads until a source is confirmed.
        if (result.needs_review) {
          fail(
            `${item.title}: no source was reliable enough. The series is waiting in Review — confirm the source there${
              download ? ' and the download starts' : ''
            }.`,
          )
        } else {
          report(
            `${item.title} added.${
              download
                ? ' Its chapters are queued under Downloads.'
                : ' Nothing is downloading — start it from the series page when you want it.'
            }`,
          )
        }
        onChanged()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(null)
      }
    },
    [clear, fail, onChanged, report, reportFailure],
  )

  const dismiss = useCallback(
    async (item: Approvable) => {
      setBusy(item.id)
      clear()
      try {
        await api.dismissSuggestion(item.id)
        onChanged()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(null)
      }
    },
    [clear, onChanged, reportFailure],
  )

  return { busy, approve, dismiss }
}

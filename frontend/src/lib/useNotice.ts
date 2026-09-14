import { useCallback, useState } from 'react'

import { messageOf } from './api'

export type NoticeTone = 'info' | 'error'

export interface Notice {
  text: string
  tone: NoticeTone
}

/**
 * The outcome of a control, as opposed to the state of a screen's data: "sync
 * queued", or the reason a click did nothing. The tone is part of the notice
 * rather than left to the call site because a failure that renders with the
 * success styling is the exact bug this replaces.
 */
export function useNotice() {
  const [notice, setNotice] = useState<Notice | null>(null)

  const report = useCallback((text: string) => setNotice({ text, tone: 'info' }), [])
  const fail = useCallback((text: string) => setNotice({ text, tone: 'error' }), [])
  const reportFailure = useCallback((failure: unknown) => fail(messageOf(failure)), [fail])
  const clear = useCallback(() => setNotice(null), [])

  return { notice, report, fail, reportFailure, clear }
}

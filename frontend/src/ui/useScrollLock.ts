import { useEffect } from 'react'

/**
 * Hold the page still under an overlay.
 *
 * Without this a bottom sheet hands its overscroll to the list behind it, and
 * the user closes the sheet to find the list somewhere else entirely.
 *
 * The depth counter is what makes two overlays safe: the second to open must
 * not restore the page when it closes, only the last one out may. It is module
 * state rather than per-component state because the two of them never share a
 * React subtree.
 */
let depth = 0
let restore: (() => void) | null = null

function lock(): void {
  if (depth++ > 0) return
  const { body, documentElement } = document
  const previousOverflow = body.style.overflow
  const previousPadding = body.style.paddingRight
  // Hiding the overflow takes the scrollbar away with it, and everything under
  // the sheet jumps right by its width. Holding the space keeps it still.
  // Overlay scrollbars — every phone, which is where the sheet lives — measure
  // zero here and get no padding at all.
  const gutter = window.innerWidth - documentElement.clientWidth
  body.style.overflow = 'hidden'
  if (gutter > 0) body.style.paddingRight = `${gutter}px`
  restore = () => {
    body.style.overflow = previousOverflow
    body.style.paddingRight = previousPadding
  }
}

function release(): void {
  if (depth === 0 || --depth > 0) return
  restore?.()
  restore = null
}

/**
 * Locks while `active`, and unlocks on the effect's cleanup — which React runs
 * whether the overlay closed by its own button, by Escape, by a click on the
 * backdrop, or by the route changing out from under it. There is no close path
 * that skips an unmount, so there is none that can leave the page frozen.
 */
export function useScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) return
    lock()
    return release
  }, [active])
}

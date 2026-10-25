import { useEffect, type RefObject } from 'react'
import type { Terminal } from '@xterm/xterm'

// Finger travel before a touch counts as a scroll rather than a tap (tap must
// still reach the pane's onClick, which raises the soft keyboard).
const DRAG_THRESHOLD_PX = 8
// Momentum: start only above this release speed, decay per 16ms frame.
const MIN_FLING_PX_PER_MS = 0.3
const FRICTION_PER_FRAME = 0.95
const STOP_PX_PER_MS = 0.02

/**
 * One-finger vertical drag scrolls the terminal on touch devices.
 *
 * xterm.js only maps touch to native scrolling of its viewport, which has
 * nothing to scroll in the alternate buffer — so in full-screen TUIs (Claude
 * Code, less, vim) a drag did nothing at all, and in the normal buffer it had
 * no momentum. Drags are translated here instead: in the normal buffer they
 * move through scrollback via `scrollLines`; in the alternate buffer they are
 * replayed as wheel events so xterm forwards them to the app as mouse-wheel
 * reports (if it enabled mouse tracking) or arrow keys. Mostly-horizontal
 * drags are left alone for TerminalGrid's swipe-to-switch-pane gesture.
 */
export function useTouchScroll(
  containerRef: RefObject<HTMLElement | null>,
  terminal: Terminal | null,
  enabled: boolean,
) {
  useEffect(() => {
    const el = containerRef.current
    if (!el || !terminal || !enabled) return

    let startX = 0
    let startY = 0
    let lastY = 0
    let lastT = 0
    let velocity = 0  // px/ms, positive = content moves up (scroll toward newer output)
    let pending = 0   // px not yet converted into whole lines
    let mode: 'idle' | 'undecided' | 'scroll' | 'ignore' = 'idle'
    let raf = 0

    const cellHeight = () => {
      const h = terminal.element?.clientHeight ?? el.clientHeight
      return Math.max(1, h / Math.max(1, terminal.rows))
    }

    const scrollBy = (px: number, clientX: number, clientY: number) => {
      pending += px
      const cell = cellHeight()
      const lines = Math.trunc(pending / cell)
      if (lines === 0) return
      pending -= lines * cell
      if (terminal.buffer.active.type === 'alternate') {
        terminal.element?.querySelector('.xterm-screen')?.dispatchEvent(
          new WheelEvent('wheel', {
            deltaY: lines * cell, deltaMode: 0, clientX, clientY,
            bubbles: true, cancelable: true,
          }),
        )
      } else {
        terminal.scrollLines(lines)
      }
    }

    const stopFling = () => {
      if (raf) cancelAnimationFrame(raf)
      raf = 0
    }

    const fling = (x: number, y: number) => {
      let prev = performance.now()
      const step = (now: number) => {
        const dt = Math.max(1, now - prev)
        prev = now
        scrollBy(velocity * dt, x, y)
        velocity *= Math.pow(FRICTION_PER_FRAME, dt / 16)
        raf = Math.abs(velocity) > STOP_PX_PER_MS ? requestAnimationFrame(step) : 0
      }
      raf = requestAnimationFrame(step)
    }

    const onStart = (e: TouchEvent) => {
      stopFling()
      if (e.touches.length !== 1) { mode = 'ignore'; return }
      const t = e.touches[0]
      startX = t.clientX
      startY = lastY = t.clientY
      lastT = e.timeStamp
      velocity = 0
      pending = 0
      mode = 'undecided'
    }

    const onMove = (e: TouchEvent) => {
      if (mode === 'idle' || mode === 'ignore' || e.touches.length !== 1) return
      const t = e.touches[0]
      if (mode === 'undecided') {
        const dx = t.clientX - startX
        const dy = t.clientY - startY
        if (Math.abs(dx) < DRAG_THRESHOLD_PX && Math.abs(dy) < DRAG_THRESHOLD_PX) return
        mode = Math.abs(dy) >= Math.abs(dx) ? 'scroll' : 'ignore'
        if (mode === 'ignore') return
      }
      e.preventDefault()
      const delta = lastY - t.clientY
      const dt = Math.max(1, e.timeStamp - lastT)
      // Light smoothing so one jittery sample doesn't decide the fling speed.
      velocity = 0.8 * (delta / dt) + 0.2 * velocity
      lastY = t.clientY
      lastT = e.timeStamp
      scrollBy(delta, t.clientX, t.clientY)
    }

    const onEnd = (e: TouchEvent) => {
      if (mode === 'scroll') {
        // Suppress the synthetic click so a scroll doesn't count as a tap.
        if (e.cancelable) e.preventDefault()
        // A pause before lifting the finger means no fling.
        if (e.timeStamp - lastT < 100 && Math.abs(velocity) > MIN_FLING_PX_PER_MS) {
          const t = e.changedTouches[0]
          fling(t?.clientX ?? 0, t?.clientY ?? 0)
        }
      }
      mode = 'idle'
    }

    // Capture phase + non-passive: we must see the gesture before xterm's own
    // listeners and be allowed to preventDefault the page scroll / bounce.
    const opts = { capture: true, passive: false } as const
    el.addEventListener('touchstart', onStart, opts)
    el.addEventListener('touchmove', onMove, opts)
    el.addEventListener('touchend', onEnd, opts)
    el.addEventListener('touchcancel', onEnd, opts)
    return () => {
      stopFling()
      el.removeEventListener('touchstart', onStart, opts)
      el.removeEventListener('touchmove', onMove, opts)
      el.removeEventListener('touchend', onEnd, opts)
      el.removeEventListener('touchcancel', onEnd, opts)
    }
  }, [containerRef, terminal, enabled])
}

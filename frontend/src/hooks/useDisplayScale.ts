import { useEffect } from 'react'
import { useDisplayStore, ROOT_FONT_PX } from '@/store/displayStore'

/**
 * Applies the UI zoom to the document root and wires the zoom keyboard
 * shortcuts. Mount once, at the app root.
 *
 * Scaling the <html> font size (rather than a CSS transform) keeps layout,
 * hit targets and scrolling native — every rem-based Tailwind utility in the
 * app grows with it. Terminal text is handled separately in TerminalPane,
 * since xterm.js needs an explicit px font size to measure its cell grid.
 */
export function useDisplayScale() {
  const uiScale = useDisplayStore((s) => s.uiScale)
  const step = useDisplayStore((s) => s.step)
  const reset = useDisplayStore((s) => s.reset)

  useEffect(() => {
    document.documentElement.style.fontSize = `${ROOT_FONT_PX * uiScale}px`
  }, [uiScale])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey) return
      // '=' is the unshifted '+' key; 'Add'/'Subtract' come from the numpad.
      const bigger = e.key === '+' || e.key === '=' || e.key === 'Add'
      const smaller = e.key === '-' || e.key === '_' || e.key === 'Subtract'
      const isReset = e.key === '0'
      if (!bigger && !smaller && !isReset) return
      // Capture phase + stopPropagation keeps xterm's textarea handler from
      // also seeing the keystroke and forwarding it to the PTY.
      e.preventDefault()
      e.stopPropagation()
      if (isReset) reset()
      else step(bigger ? 1 : -1)
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [step, reset])
}

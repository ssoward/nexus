import { useEffect } from 'react'

// iOS Safari ignores interactive-widget=resizes-content: the soft keyboard
// overlays the page without shrinking dvh or the layout viewport, so the
// bottom of the terminal (cursor line, typed text) ends up hidden behind it.
// visualViewport is the only keyboard signal iOS exposes — mirror its height
// into --app-height so the root layout sizes itself to the truly visible area.
// vv.height * vv.scale keeps pinch-zoom from shrinking the layout: zooming
// changes height and scale inversely, while the keyboard only changes height.
export function useVisualViewportHeight(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    const vv = window.visualViewport
    if (!vv) return
    const root = document.documentElement
    const update = () => {
      root.style.setProperty('--app-height', `${Math.round(vv.height * vv.scale)}px`)
      // iOS can still nudge the page upward when the keyboard opens even
      // though the focused (hidden) input sits at top:0 — clamp it back.
      if (window.scrollY !== 0) window.scrollTo(0, 0)
    }
    update()
    vv.addEventListener('resize', update)
    vv.addEventListener('scroll', update)
    return () => {
      vv.removeEventListener('resize', update)
      vv.removeEventListener('scroll', update)
      root.style.removeProperty('--app-height')
    }
  }, [enabled])
}

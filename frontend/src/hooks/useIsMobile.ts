import { useEffect, useState } from 'react'

const BREAKPOINT = 1024 // lg — overlay sidebar below this width

function _check(): boolean {
  // Treat any touch-primary device as mobile regardless of viewport width,
  // so tablets and "Request Desktop Site" mode in iOS Safari are handled.
  const isTouch = window.matchMedia('(pointer: coarse)').matches
  return isTouch || window.innerWidth < BREAKPOINT
}

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(_check)

  useEffect(() => {
    const mqWidth = window.matchMedia(`(max-width: ${BREAKPOINT - 1}px)`)
    const mqTouch = window.matchMedia('(pointer: coarse)')
    const handler = () => setIsMobile(_check())
    mqWidth.addEventListener('change', handler)
    mqTouch.addEventListener('change', handler)
    return () => {
      mqWidth.removeEventListener('change', handler)
      mqTouch.removeEventListener('change', handler)
    }
  }, [])

  return isMobile
}

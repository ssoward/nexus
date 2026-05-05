import { useEffect, useState } from 'react'

// Treat any touch-primary device as mobile (pointer: coarse covers phones and
// tablets regardless of viewport width, including iOS "Request Desktop Site").
// Keep a 640px hard floor so genuinely tiny screens (< sm breakpoint) still
// get mobile layout even without touch support.
function _check(): boolean {
  return (
    window.matchMedia('(pointer: coarse)').matches ||
    window.innerWidth < 640
  )
}

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(_check)

  useEffect(() => {
    const mqTouch = window.matchMedia('(pointer: coarse)')
    const mqWidth = window.matchMedia('(max-width: 639px)')
    const handler = () => setIsMobile(_check())
    mqTouch.addEventListener('change', handler)
    mqWidth.addEventListener('change', handler)
    return () => {
      mqTouch.removeEventListener('change', handler)
      mqWidth.removeEventListener('change', handler)
    }
  }, [])

  return isMobile
}

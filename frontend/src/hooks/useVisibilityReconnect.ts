import { useEffect, useRef } from 'react'
import { refreshToken } from '@/api/auth'

const AWAY_THRESHOLD_MS = 5_000

interface Options {
  onBrowserReturn: () => void
  enabled: boolean
}

export function useVisibilityReconnect({ onBrowserReturn, enabled }: Options) {
  const lastHiddenAt = useRef<number>(0)

  useEffect(() => {
    if (!enabled) return

    const handleVisibility = async () => {
      if (document.hidden) {
        lastHiddenAt.current = Date.now()
        return
      }
      // Tab became visible
      if (lastHiddenAt.current === 0) return
      const away = Date.now() - lastHiddenAt.current
      if (away < AWAY_THRESHOLD_MS) return

      // Refresh JWT before attempting WS reconnect
      try {
        await refreshToken()
      } catch {
        // If refresh fails, the reconnect will fail with 401 and redirect to login
      }
      onBrowserReturn()
    }

    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [onBrowserReturn, enabled])
}

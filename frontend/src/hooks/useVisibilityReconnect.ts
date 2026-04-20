import { useEffect, useRef } from 'react'

const AWAY_THRESHOLD_MS = 5_000
const RECONNECT_COOLDOWN_MS = 15_000

interface Options {
  onBrowserReturn: () => void
  enabled: boolean
}

export function useVisibilityReconnect({ onBrowserReturn, enabled }: Options) {
  const lastHiddenAt = useRef<number>(0)
  const lastReconnectAt = useRef<number>(0)

  useEffect(() => {
    if (!enabled) return

    const handleVisibility = () => {
      if (document.hidden) {
        lastHiddenAt.current = Date.now()
        return
      }
      // Tab became visible
      if (lastHiddenAt.current === 0) return
      const now = Date.now()
      const away = now - lastHiddenAt.current
      if (away < AWAY_THRESHOLD_MS) return
      // Cooldown prevents rapid reconnect churn
      if (now - lastReconnectAt.current < RECONNECT_COOLDOWN_MS) return

      lastReconnectAt.current = now
      // JWT refresh is handled by useAuth's visibility handler;
      // no duplicate refresh here.
      onBrowserReturn()
    }

    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [onBrowserReturn, enabled])
}

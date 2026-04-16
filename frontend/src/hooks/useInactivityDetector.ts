import { useEffect, useState } from 'react'
import { useSessionStore } from '@/store/sessionStore'

const IDLE_THRESHOLD_MS = 60_000
const POLL_INTERVAL_MS = 1000

/**
 * Returns whether a session is idle (no terminal output for IDLE_THRESHOLD_MS).
 * Only considers sessions with status "running".
 */
export function useInactivityDetector(sessionId: string, status: string) {
  const timestamp = useSessionStore((s) => s.lastOutputTimestamps[sessionId])
  const [isIdle, setIsIdle] = useState(false)

  useEffect(() => {
    if (status !== 'running') {
      setIsIdle(false)
      return
    }

    const check = () => {
      if (!timestamp) {
        // No output yet — not idle (session just started)
        setIsIdle(false)
        return
      }
      setIsIdle(Date.now() - timestamp > IDLE_THRESHOLD_MS)
    }

    check()
    const id = setInterval(check, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [timestamp, status])

  return isIdle
}

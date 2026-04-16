import { useEffect, useRef } from 'react'
import { useSessionStore } from '@/store/sessionStore'
import type { Session } from '@/types/session'

const PROMOTE_DELAY_MS = 2000
const IDLE_THRESHOLD_MS = 60_000

/**
 * When the primary session is idle and autoPromote is enabled,
 * promotes the most-recently-active non-idle session after a short delay.
 */
export function useAutoPromote(sessions: Session[]) {
  const {
    layoutMode,
    primarySessionId,
    autoPromote,
    lastOutputTimestamps,
    setPrimarySession,
  } = useSessionStore()

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (layoutMode !== 'priority' || !autoPromote || !primarySessionId) return
    if (sessions.length < 2) return

    const check = () => {
      const now = Date.now()
      const primaryTs = lastOutputTimestamps[primarySessionId]

      // Primary is not idle yet
      if (primaryTs && now - primaryTs < IDLE_THRESHOLD_MS) return

      // Find best candidate: non-idle, most recent output
      const candidates = sessions
        .filter((s) => s.id !== primarySessionId && s.status === 'running')
        .map((s) => ({ id: s.id, ts: lastOutputTimestamps[s.id] ?? 0 }))
        .filter((c) => now - c.ts < IDLE_THRESHOLD_MS)
        .sort((a, b) => b.ts - a.ts)

      if (candidates.length > 0) {
        // Delay promotion to avoid flicker
        if (!timerRef.current) {
          timerRef.current = setTimeout(() => {
            timerRef.current = null
            // Re-check: primary might have become active during delay
            const currentPrimaryTs = useSessionStore.getState().lastOutputTimestamps[primarySessionId]
            if (currentPrimaryTs && Date.now() - currentPrimaryTs < IDLE_THRESHOLD_MS) return
            setPrimarySession(candidates[0].id)
          }, PROMOTE_DELAY_MS)
        }
      }
    }

    const id = setInterval(check, 1000)
    return () => {
      clearInterval(id)
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [layoutMode, autoPromote, primarySessionId, sessions, lastOutputTimestamps, setPrimarySession])
}

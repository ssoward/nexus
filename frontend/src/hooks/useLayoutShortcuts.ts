import { useEffect } from 'react'
import { useSessionStore, activeIndexIn } from '@/store/sessionStore'
import type { Session } from '@/types/session'

export type ShortcutAction =
  | { kind: 'select'; index: number }
  | { kind: 'cycle'; delta: 1 | -1 }
  | { kind: 'toggleFocus' }
  | { kind: 'toggleFullscreen' }

/**
 * Map a keydown to a layout action, or null if it isn't one of ours.
 *
 *   Ctrl/Cmd + 1–6           jump to shell N
 *   Ctrl/Cmd + Shift + [ / ] previous / next shell
 *   Ctrl/Cmd + Shift + Enter toggle focus (one shell) ↔ multi-shell layout
 *   Ctrl/Cmd + Shift + F     toggle full screen (hide sidebar + header)
 *
 * Esc is deliberately never bound — vim, less and Claude Code need it.
 */
export function shortcutFor(e: Pick<KeyboardEvent, 'key' | 'code' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>): ShortcutAction | null {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return null
  if (!e.shiftKey && e.key >= '1' && e.key <= '6' && e.key.length === 1) {
    return { kind: 'select', index: parseInt(e.key, 10) - 1 }
  }
  if (!e.shiftKey) return null
  // e.code: Shift turns '[' into '{' (and differs per keyboard layout).
  if (e.code === 'BracketLeft') return { kind: 'cycle', delta: -1 }
  if (e.code === 'BracketRight') return { kind: 'cycle', delta: 1 }
  if (e.key === 'Enter') return { kind: 'toggleFocus' }
  if (e.code === 'KeyF') return { kind: 'toggleFullscreen' }
  return null
}

/**
 * Global layout shortcuts. Registered in the capture phase with
 * stopPropagation (same as the display-zoom keys) so xterm's textarea never
 * sees them and forwards them to the shell.
 */
export function useLayoutShortcuts(sessions: Session[], onToggleFullscreen: () => void) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const action = shortcutFor(e)
      if (!action) return
      const st = useSessionStore.getState()
      if (action.kind === 'select') {
        const target = sessions[action.index]
        if (!target) return // let the key through if there's no such shell
        st.setActiveSession(target.id)
      } else if (action.kind === 'cycle') {
        if (sessions.length < 2) return
        const idx = activeIndexIn(sessions, st.activeSessionId)
        const next = sessions[(idx + action.delta + sessions.length) % sessions.length]
        st.setActiveSession(next.id)
      } else if (action.kind === 'toggleFocus') {
        st.toggleFocus()
      } else {
        onToggleFullscreen()
      }
      e.preventDefault()
      e.stopPropagation()
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [sessions, onToggleFullscreen])
}

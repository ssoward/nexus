import { create } from 'zustand'
import type { Session, SessionStatus } from '@/types/session'

/**
 * grid     — every attached shell visible, equal size
 * priority — one large primary pane + thumbnails (auto-promote optional)
 * focus    — one shell fills the terminal area; a tab strip switches between them
 */
export type LayoutMode = 'grid' | 'priority' | 'focus'

/**
 * Sessions that get a terminal pane. `recovery_pending` sessions are included
 * because mounting a pane is what triggers their lazy respawn on the backend.
 */
export function attachedSessions(sessions: Session[]): Session[] {
  return sessions.filter((s) => s.status === 'running' || s.status === 'recovery_pending')
}

/** Index of the active session within `list`, falling back to 0. */
export function activeIndexIn(list: Session[], activeSessionId: string | null): number {
  const idx = activeSessionId ? list.findIndex((s) => s.id === activeSessionId) : -1
  return idx >= 0 ? idx : 0
}

interface SessionState {
  sessions: Session[]
  /** The shell that has focus. Tracked by id (not index) so it survives
   *  sessions being added, removed, or filtered out of the attached list. */
  activeSessionId: string | null
  // Inactivity tracking (Phase 1)
  lastOutputTimestamps: Record<string, number>
  // Layout (Phase 2)
  layoutMode: LayoutMode
  /** Layout to return to when focus mode is toggled off. */
  multiLayoutMode: Exclude<LayoutMode, 'focus'>
  primarySessionId: string | null
  autoPromote: boolean
  /** Full-screen: hide sidebar, header and embedded pages so shells get the whole window. */
  immersive: boolean

  setSessions: (sessions: Session[]) => void
  addSession: (session: Session) => void
  removeSession: (id: string) => void
  updateSessionStatus: (id: string, status: SessionStatus) => void
  /** Make `id` the active shell; in priority layout it also becomes the primary pane. */
  setActiveSession: (id: string | null) => void
  markSessionOutput: (id: string) => void
  setLayoutMode: (mode: LayoutMode) => void
  /** Toggle between focus (single shell) and the last multi-shell layout. */
  toggleFocus: () => void
  setPrimarySession: (id: string | null) => void
  setAutoPromote: (enabled: boolean) => void
  setImmersive: (on: boolean) => void
}

function layoutChange(s: SessionState, mode: LayoutMode): Partial<SessionState> {
  const next: Partial<SessionState> = { layoutMode: mode }
  if (mode !== 'focus') next.multiLayoutMode = mode
  // Leaving priority for focus: the big pane (which auto-promote may have
  // changed) is the shell the user is looking at, so that's the one to maximise.
  if (mode === 'focus' && s.layoutMode === 'priority' && s.primarySessionId) {
    next.activeSessionId = s.primarySessionId
  }
  // Entering priority: the shell that had focus becomes the primary pane.
  if (mode === 'priority' && s.activeSessionId) next.primarySessionId = s.activeSessionId
  return next
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  activeSessionId: null,
  lastOutputTimestamps: {},
  layoutMode: 'grid',
  multiLayoutMode: 'grid',
  primarySessionId: null,
  autoPromote: true,
  immersive: false,

  setSessions: (sessions) => set({ sessions }),
  addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) =>
    set((s) => {
      const { [id]: _, ...rest } = s.lastOutputTimestamps
      let activeSessionId = s.activeSessionId
      if (activeSessionId === id) {
        // Hand focus to the neighbouring attached shell rather than jumping to the first.
        const attached = attachedSessions(s.sessions)
        const idx = attached.findIndex((x) => x.id === id)
        const next = attached[idx + 1] ?? attached[idx - 1]
        activeSessionId = next?.id ?? null
      }
      return {
        sessions: s.sessions.filter((x) => x.id !== id),
        activeSessionId,
        lastOutputTimestamps: rest,
        primarySessionId: s.primarySessionId === id ? null : s.primarySessionId,
      }
    }),
  updateSessionStatus: (id, status) =>
    set((s) => ({
      sessions: s.sessions.map((x) => (x.id === id ? { ...x, status } : x)),
    })),
  setActiveSession: (id) =>
    set((s) => ({
      activeSessionId: id,
      primarySessionId: s.layoutMode === 'priority' && id ? id : s.primarySessionId,
    })),
  markSessionOutput: (id) =>
    set((s) => ({
      lastOutputTimestamps: { ...s.lastOutputTimestamps, [id]: Date.now() },
    })),
  setLayoutMode: (mode) => set((s) => layoutChange(s, mode)),
  toggleFocus: () =>
    set((s) => layoutChange(s, s.layoutMode === 'focus' ? s.multiLayoutMode : 'focus')),
  setPrimarySession: (id) => set({ primarySessionId: id }),
  setAutoPromote: (enabled) => set({ autoPromote: enabled }),
  setImmersive: (on) => set({ immersive: on }),
}))

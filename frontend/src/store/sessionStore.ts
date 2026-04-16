import { create } from 'zustand'
import type { Session, SessionStatus } from '@/types/session'

type LayoutMode = 'grid' | 'priority'

interface SessionState {
  sessions: Session[]
  activePaneIndex: number
  // Inactivity tracking (Phase 1)
  lastOutputTimestamps: Record<string, number>
  // Layout (Phase 2)
  layoutMode: LayoutMode
  primarySessionId: string | null
  autoPromote: boolean

  setSessions: (sessions: Session[]) => void
  addSession: (session: Session) => void
  removeSession: (id: string) => void
  updateSessionStatus: (id: string, status: SessionStatus) => void
  setActivePane: (index: number) => void
  markSessionOutput: (id: string) => void
  setLayoutMode: (mode: LayoutMode) => void
  setPrimarySession: (id: string | null) => void
  setAutoPromote: (enabled: boolean) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  activePaneIndex: 0,
  lastOutputTimestamps: {},
  layoutMode: 'grid',
  primarySessionId: null,
  autoPromote: true,

  setSessions: (sessions) => set({ sessions }),
  addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) =>
    set((s) => {
      const { [id]: _, ...rest } = s.lastOutputTimestamps
      return {
        sessions: s.sessions.filter((x) => x.id !== id),
        activePaneIndex: Math.max(0, s.activePaneIndex - 1),
        lastOutputTimestamps: rest,
        primarySessionId: s.primarySessionId === id ? null : s.primarySessionId,
      }
    }),
  updateSessionStatus: (id, status) =>
    set((s) => ({
      sessions: s.sessions.map((x) => (x.id === id ? { ...x, status } : x)),
    })),
  setActivePane: (index) => set({ activePaneIndex: index }),
  markSessionOutput: (id) =>
    set((s) => ({
      lastOutputTimestamps: { ...s.lastOutputTimestamps, [id]: Date.now() },
    })),
  setLayoutMode: (mode) => set({ layoutMode: mode }),
  setPrimarySession: (id) => set({ primarySessionId: id }),
  setAutoPromote: (enabled) => set({ autoPromote: enabled }),
}))

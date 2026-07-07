import { describe, it, expect, beforeEach } from 'vitest'
import { useSessionStore } from './sessionStore'
import type { Session } from '@/types/session'

function makeSession(id: string, over: Partial<Session> = {}): Session {
  return {
    id,
    name: `s-${id}`,
    image: 'bash',
    status: 'running',
    cols: 80,
    rows: 24,
    created_at: '2026-01-01T00:00:00Z',
    last_active_at: '2026-01-01T00:00:00Z',
    ...over,
  } as Session
}

describe('sessionStore', () => {
  beforeEach(() => {
    useSessionStore.setState({
      sessions: [],
      activePaneIndex: 0,
      lastOutputTimestamps: {},
      layoutMode: 'grid',
      primarySessionId: null,
      autoPromote: true,
    })
  })

  it('addSession appends', () => {
    useSessionStore.getState().addSession(makeSession('a'))
    useSessionStore.getState().addSession(makeSession('b'))
    expect(useSessionStore.getState().sessions.map((s) => s.id)).toEqual(['a', 'b'])
  })

  it('setSessions replaces the list', () => {
    useSessionStore.getState().addSession(makeSession('a'))
    useSessionStore.getState().setSessions([makeSession('x'), makeSession('y')])
    expect(useSessionStore.getState().sessions.map((s) => s.id)).toEqual(['x', 'y'])
  })

  it('updateSessionStatus mutates only the matching session', () => {
    useSessionStore.getState().setSessions([makeSession('a'), makeSession('b')])
    useSessionStore.getState().updateSessionStatus('b', 'stopped')
    const byId = Object.fromEntries(useSessionStore.getState().sessions.map((s) => [s.id, s.status]))
    expect(byId).toEqual({ a: 'running', b: 'stopped' })
  })

  it('removeSession drops it, clears its timestamp, and resets primary', () => {
    useSessionStore.getState().setSessions([makeSession('a'), makeSession('b')])
    useSessionStore.getState().markSessionOutput('b')
    useSessionStore.getState().setPrimarySession('b')
    useSessionStore.getState().removeSession('b')
    const st = useSessionStore.getState()
    expect(st.sessions.map((s) => s.id)).toEqual(['a'])
    expect(st.lastOutputTimestamps['b']).toBeUndefined()
    expect(st.primarySessionId).toBeNull()
  })

  it('removeSession keeps a different primary session', () => {
    useSessionStore.getState().setSessions([makeSession('a'), makeSession('b')])
    useSessionStore.getState().setPrimarySession('a')
    useSessionStore.getState().removeSession('b')
    expect(useSessionStore.getState().primarySessionId).toBe('a')
  })

  it('markSessionOutput records a timestamp', () => {
    useSessionStore.getState().markSessionOutput('a')
    expect(typeof useSessionStore.getState().lastOutputTimestamps['a']).toBe('number')
  })

  it('layout controls update state', () => {
    useSessionStore.getState().setLayoutMode('priority')
    useSessionStore.getState().setAutoPromote(false)
    useSessionStore.getState().setActivePane(3)
    const st = useSessionStore.getState()
    expect(st.layoutMode).toBe('priority')
    expect(st.autoPromote).toBe(false)
    expect(st.activePaneIndex).toBe(3)
  })
})

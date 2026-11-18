import { describe, it, expect, beforeEach } from 'vitest'
import { useSessionStore, attachedSessions, activeIndexIn } from './sessionStore'
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
      activeSessionId: null,
      lastOutputTimestamps: {},
      layoutMode: 'grid',
      multiLayoutMode: 'grid',
      immersive: false,
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
    useSessionStore.getState().setActiveSession('c')
    const st = useSessionStore.getState()
    expect(st.layoutMode).toBe('priority')
    expect(st.autoPromote).toBe(false)
    expect(st.activeSessionId).toBe('c')
  })

  it('setActiveSession promotes to primary only in priority layout', () => {
    useSessionStore.getState().setActiveSession('a')
    expect(useSessionStore.getState().primarySessionId).toBeNull()
    useSessionStore.getState().setLayoutMode('priority')
    useSessionStore.getState().setActiveSession('b')
    expect(useSessionStore.getState().primarySessionId).toBe('b')
  })

  it('toggleFocus returns to the last multi-shell layout', () => {
    const st = () => useSessionStore.getState()
    st().toggleFocus()
    expect(st().layoutMode).toBe('focus')
    st().toggleFocus()
    expect(st().layoutMode).toBe('grid')
    st().setLayoutMode('priority')
    st().toggleFocus()
    expect(st().layoutMode).toBe('focus')
    st().toggleFocus()
    expect(st().layoutMode).toBe('priority')
  })

  it('priority → focus maximises the primary pane', () => {
    const st = () => useSessionStore.getState()
    st().setActiveSession('a')
    st().setLayoutMode('priority')
    st().setPrimarySession('b') // e.g. auto-promote
    st().setLayoutMode('focus')
    expect(st().activeSessionId).toBe('b')
  })

  it('removeSession hands focus to the neighbouring attached shell', () => {
    const st = () => useSessionStore.getState()
    st().setSessions([makeSession('a'), makeSession('x', { status: 'stopped' }), makeSession('b'), makeSession('c')])
    st().setActiveSession('b')
    st().removeSession('b')
    expect(st().activeSessionId).toBe('c')
    st().removeSession('c')
    expect(st().activeSessionId).toBe('a')
    st().removeSession('a')
    expect(st().activeSessionId).toBeNull()
  })

  it('removeSession of a non-active shell keeps the active one', () => {
    const st = () => useSessionStore.getState()
    st().setSessions([makeSession('a'), makeSession('b'), makeSession('c')])
    st().setActiveSession('a')
    st().removeSession('c')
    expect(st().activeSessionId).toBe('a')
  })
})

describe('attachedSessions / activeIndexIn', () => {
  it('keeps running + recovery_pending, in order', () => {
    const list = [
      makeSession('a'),
      makeSession('b', { status: 'stopped' }),
      makeSession('c', { status: 'recovery_pending' }),
      makeSession('d', { status: 'error' }),
    ]
    expect(attachedSessions(list).map((s) => s.id)).toEqual(['a', 'c'])
  })

  it('falls back to index 0 for unknown / null ids', () => {
    const list = [makeSession('a'), makeSession('b')]
    expect(activeIndexIn(list, 'b')).toBe(1)
    expect(activeIndexIn(list, 'zzz')).toBe(0)
    expect(activeIndexIn(list, null)).toBe(0)
  })
})

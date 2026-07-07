import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAutoPromote } from './useAutoPromote'
import { useSessionStore } from '@/store/sessionStore'
import type { Session } from '@/types/session'

function s(id: string): Session {
  return {
    id, name: id, image: 'bash', status: 'running',
    cols: 80, rows: 24, created_at: '', last_active_at: '',
  } as Session
}

function reset(over = {}) {
  useSessionStore.setState({
    sessions: [], activePaneIndex: 0, lastOutputTimestamps: {},
    layoutMode: 'priority', primarySessionId: 'a', autoPromote: true, ...over,
  })
}

describe('useAutoPromote', () => {
  beforeEach(() => { reset(); vi.useFakeTimers() })
  afterEach(() => vi.useRealTimers())

  it('does nothing when not in priority layout', () => {
    reset({ layoutMode: 'grid' })
    renderHook(() => useAutoPromote([s('a'), s('b')]))
    act(() => { vi.advanceTimersByTime(5000) })
    expect(useSessionStore.getState().primarySessionId).toBe('a')
  })

  it('does nothing when autoPromote is off', () => {
    reset({ autoPromote: false })
    renderHook(() => useAutoPromote([s('a'), s('b')]))
    act(() => { vi.advanceTimersByTime(5000) })
    expect(useSessionStore.getState().primarySessionId).toBe('a')
  })

  it('promotes an active session when the idle primary times out', () => {
    const now = Date.now()
    // primary "a" is stale (idle), "b" produced output recently
    reset({ lastOutputTimestamps: { a: now - 120_000, b: now } })
    renderHook(() => useAutoPromote([s('a'), s('b')]))
    // poll fires (1s) → schedules promote (2s delay) → fires
    act(() => { vi.advanceTimersByTime(1000) })
    act(() => { vi.advanceTimersByTime(2000) })
    expect(useSessionStore.getState().primarySessionId).toBe('b')
  })

  it('does not promote while the primary is still active', () => {
    const now = Date.now()
    reset({ lastOutputTimestamps: { a: now, b: now } })
    renderHook(() => useAutoPromote([s('a'), s('b')]))
    act(() => { vi.advanceTimersByTime(4000) })
    expect(useSessionStore.getState().primarySessionId).toBe('a')
  })

  it('does not promote when there is only one session', () => {
    const now = Date.now()
    reset({ lastOutputTimestamps: { a: now - 120_000 } })
    renderHook(() => useAutoPromote([s('a')]))
    act(() => { vi.advanceTimersByTime(4000) })
    expect(useSessionStore.getState().primarySessionId).toBe('a')
  })
})

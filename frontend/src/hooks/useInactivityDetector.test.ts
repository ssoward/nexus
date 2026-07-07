import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useInactivityDetector } from './useInactivityDetector'
import { useSessionStore } from '@/store/sessionStore'

describe('useInactivityDetector', () => {
  beforeEach(() => {
    useSessionStore.setState({ lastOutputTimestamps: {} })
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('is not idle when status is not running', () => {
    const { result } = renderHook(() => useInactivityDetector('s1', 'stopped'))
    expect(result.current).toBe(false)
  })

  it('is not idle when there is no output yet', () => {
    const { result } = renderHook(() => useInactivityDetector('s1', 'running'))
    expect(result.current).toBe(false)
  })

  it('is not idle shortly after output', () => {
    useSessionStore.setState({ lastOutputTimestamps: { s1: Date.now() } })
    const { result } = renderHook(() => useInactivityDetector('s1', 'running'))
    act(() => { vi.advanceTimersByTime(5_000) })
    expect(result.current).toBe(false)
  })

  it('becomes idle after the 60s threshold with no new output', () => {
    useSessionStore.setState({ lastOutputTimestamps: { s1: Date.now() } })
    const { result } = renderHook(() => useInactivityDetector('s1', 'running'))
    act(() => { vi.advanceTimersByTime(61_000) })
    expect(result.current).toBe(true)
  })
})

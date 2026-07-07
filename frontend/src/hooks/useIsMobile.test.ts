import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useIsMobile } from './useIsMobile'

function mockMatchMedia(coarse: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('coarse') ? coarse : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

describe('useIsMobile', () => {
  const originalWidth = window.innerWidth
  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { value: originalWidth, configurable: true, writable: true })
  })

  it('is mobile when the pointer is coarse (touch device)', () => {
    mockMatchMedia(true)
    Object.defineProperty(window, 'innerWidth', { value: 1200, configurable: true, writable: true })
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(true)
  })

  it('is mobile on a narrow viewport even without touch', () => {
    mockMatchMedia(false)
    Object.defineProperty(window, 'innerWidth', { value: 500, configurable: true, writable: true })
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(true)
  })

  it('is not mobile on a wide non-touch screen', () => {
    mockMatchMedia(false)
    Object.defineProperty(window, 'innerWidth', { value: 1200, configurable: true, writable: true })
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)
  })
})

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDisplayScale } from './useDisplayScale'
import { useDisplayStore, ROOT_FONT_PX } from '@/store/displayStore'

const get = () => useDisplayStore.getState()

/** Dispatch a keydown the way a real browser would, so capture-phase runs. */
function press(key: string, mods: Partial<KeyboardEventInit> = {}) {
  const ev = new KeyboardEvent('keydown', {
    key,
    bubbles: true,
    cancelable: true,
    ...mods,
  })
  // act() so the store update that follows is flushed before we assert.
  act(() => {
    window.dispatchEvent(ev)
  })
  return ev
}

describe('useDisplayScale', () => {
  beforeEach(() => {
    localStorage.clear()
    get().reset()
    document.documentElement.style.fontSize = ''
  })

  describe('root font size', () => {
    it('applies the stored scale on mount', () => {
      useDisplayStore.setState({ uiScale: 1.5 })
      renderHook(() => useDisplayScale())
      expect(document.documentElement.style.fontSize).toBe(
        `${ROOT_FONT_PX * 1.5}px`
      )
    })

    it('tracks later scale changes', () => {
      const { rerender } = renderHook(() => useDisplayScale())
      expect(document.documentElement.style.fontSize).toBe(`${ROOT_FONT_PX}px`)

      act(() => get().setUiScale(1.2))
      rerender()
      expect(document.documentElement.style.fontSize).toBe(
        `${ROOT_FONT_PX * 1.2}px`
      )
    })
  })

  describe('keyboard shortcuts', () => {
    beforeEach(() => renderHook(() => useDisplayScale()))

    it.each([
      ['+', 1.1],
      ['=', 1.1],
      ['Add', 1.1],
    ])('%s zooms in', (key, expected) => {
      press(key, { metaKey: true })
      expect(get().uiScale).toBe(expected)
    })

    it.each([
      ['-', 0.9],
      ['_', 0.9],
      ['Subtract', 0.9],
    ])('%s zooms out', (key, expected) => {
      press(key, { metaKey: true })
      expect(get().uiScale).toBe(expected)
    })

    it('works with Ctrl as well as Meta', () => {
      press('+', { ctrlKey: true })
      expect(get().uiScale).toBe(1.1)
    })

    it('resets with 0', () => {
      act(() => get().setUiScale(1.8))
      press('0', { metaKey: true })
      expect(get().uiScale).toBe(1)
    })

    it('steps the terminal font size alongside the UI', () => {
      press('+', { metaKey: true })
      expect(get().terminalFontSize).toBe(15)
    })

    it('prevents the default so the browser does not also zoom', () => {
      const ev = press('+', { metaKey: true })
      expect(ev.defaultPrevented).toBe(true)
    })

    it('does not let the keystroke reach the terminal', () => {
      // TerminalPane's xterm listens on a descendant; a capture-phase
      // stopPropagation is what keeps "+" out of the PTY input stream.
      const terminalListener = vi.fn()
      document.body.addEventListener('keydown', terminalListener)
      press('+', { metaKey: true })
      expect(terminalListener).not.toHaveBeenCalled()
      document.body.removeEventListener('keydown', terminalListener)
    })
  })

  describe('keys it must ignore', () => {
    beforeEach(() => renderHook(() => useDisplayScale()))

    it('ignores an unmodified + (it is ordinary terminal input)', () => {
      const ev = press('+')
      expect(get().uiScale).toBe(1)
      expect(ev.defaultPrevented).toBe(false)
    })

    it('ignores other modified keys, letting them through to the terminal', () => {
      const ev = press('c', { ctrlKey: true })
      expect(get().uiScale).toBe(1)
      expect(ev.defaultPrevented).toBe(false)
    })

    it('ignores Alt combinations, which shells use for word motion', () => {
      const ev = press('+', { metaKey: true, altKey: true })
      expect(get().uiScale).toBe(1)
      expect(ev.defaultPrevented).toBe(false)
    })
  })

  it('removes its listener on unmount', () => {
    const { unmount } = renderHook(() => useDisplayScale())
    unmount()
    press('+', { metaKey: true })
    expect(get().uiScale).toBe(1)
  })
})

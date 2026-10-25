import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import type { Terminal } from '@xterm/xterm'
import { useTouchScroll } from './useTouchScroll'

// 10 rows in a 200px element → 20px per line.
function makeTerminal(bufferType: 'normal' | 'alternate' = 'normal') {
  const element = document.createElement('div')
  Object.defineProperty(element, 'clientHeight', { value: 200 })
  const screen = document.createElement('div')
  screen.className = 'xterm-screen'
  element.appendChild(screen)
  const term = {
    rows: 10,
    element,
    buffer: { active: { type: bufferType } },
    scrollLines: vi.fn(),
  }
  return { term: term as unknown as Terminal & { scrollLines: ReturnType<typeof vi.fn> }, screen }
}

let stamp = 0
function touch(el: HTMLElement, type: string, x: number, y: number, dtMs = 16) {
  stamp += dtMs
  const ev = new Event(type, { bubbles: true, cancelable: true })
  const point = [{ clientX: x, clientY: y }]
  Object.defineProperty(ev, 'touches', { value: type === 'touchend' ? [] : point })
  Object.defineProperty(ev, 'changedTouches', { value: point })
  Object.defineProperty(ev, 'timeStamp', { value: stamp })
  el.dispatchEvent(ev)
  return ev
}

describe('useTouchScroll', () => {
  let container: HTMLDivElement
  const ref = { current: null as HTMLDivElement | null }

  beforeEach(() => {
    container = document.createElement('div')
    ref.current = container
    // A slow drag (no fling) keeps these tests deterministic.
    stamp = 0
  })

  it('scrolls back through history when dragging down', () => {
    const { term } = makeTerminal()
    renderHook(() => useTouchScroll(ref, term, true))
    touch(container, 'touchstart', 100, 100)
    const move = touch(container, 'touchmove', 100, 160, 500)
    touch(container, 'touchend', 100, 160, 500)
    expect(term.scrollLines).toHaveBeenCalledWith(-3)
    expect(move.defaultPrevented).toBe(true)
  })

  it('scrolls toward newer output when dragging up', () => {
    const { term } = makeTerminal()
    renderHook(() => useTouchScroll(ref, term, true))
    touch(container, 'touchstart', 100, 200)
    touch(container, 'touchmove', 100, 140, 500)
    expect(term.scrollLines).toHaveBeenCalledWith(3)
  })

  it('leaves taps alone so they still raise the keyboard', () => {
    const { term } = makeTerminal()
    renderHook(() => useTouchScroll(ref, term, true))
    touch(container, 'touchstart', 100, 100)
    touch(container, 'touchmove', 102, 103)
    const end = touch(container, 'touchend', 102, 103)
    expect(term.scrollLines).not.toHaveBeenCalled()
    expect(end.defaultPrevented).toBe(false)
  })

  it('ignores horizontal swipes (pane switching)', () => {
    const { term } = makeTerminal()
    renderHook(() => useTouchScroll(ref, term, true))
    touch(container, 'touchstart', 100, 100)
    const move = touch(container, 'touchmove', 200, 120)
    expect(term.scrollLines).not.toHaveBeenCalled()
    expect(move.defaultPrevented).toBe(false)
  })

  it('replays drags as wheel events in the alternate buffer', () => {
    const { term, screen } = makeTerminal('alternate')
    const wheel = vi.fn()
    screen.addEventListener('wheel', (e) => wheel((e as WheelEvent).deltaY))
    renderHook(() => useTouchScroll(ref, term, true))
    touch(container, 'touchstart', 100, 100)
    touch(container, 'touchmove', 100, 140, 500)
    expect(wheel).toHaveBeenCalledWith(-40)
    expect(term.scrollLines).not.toHaveBeenCalled()
  })

  it('does nothing when disabled', () => {
    const { term } = makeTerminal()
    renderHook(() => useTouchScroll(ref, term, false))
    touch(container, 'touchstart', 100, 100)
    touch(container, 'touchmove', 100, 160, 500)
    expect(term.scrollLines).not.toHaveBeenCalled()
  })
})

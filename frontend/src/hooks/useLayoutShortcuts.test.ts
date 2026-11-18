import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { shortcutFor, useLayoutShortcuts } from './useLayoutShortcuts'
import { useSessionStore } from '@/store/sessionStore'
import type { Session } from '@/types/session'

const k = (over: Partial<KeyboardEvent>) => ({
  key: '', code: '', ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...over,
})

function makeSession(id: string): Session {
  return {
    id, name: id, image: 'bash', status: 'running', cols: 80, rows: 24,
    created_at: '', last_active_at: '',
  } as Session
}

describe('shortcutFor', () => {
  it('maps Ctrl/Cmd+digit to select', () => {
    expect(shortcutFor(k({ key: '3', ctrlKey: true }))).toEqual({ kind: 'select', index: 2 })
    expect(shortcutFor(k({ key: '1', metaKey: true }))).toEqual({ kind: 'select', index: 0 })
    expect(shortcutFor(k({ key: '7', ctrlKey: true }))).toBeNull()
  })

  it('maps Ctrl/Cmd+Shift combos', () => {
    expect(shortcutFor(k({ key: 'Enter', ctrlKey: true, shiftKey: true }))).toEqual({ kind: 'toggleFocus' })
    expect(shortcutFor(k({ key: 'F', code: 'KeyF', metaKey: true, shiftKey: true }))).toEqual({ kind: 'toggleFullscreen' })
    expect(shortcutFor(k({ key: '{', code: 'BracketLeft', ctrlKey: true, shiftKey: true }))).toEqual({ kind: 'cycle', delta: -1 })
    expect(shortcutFor(k({ key: '}', code: 'BracketRight', ctrlKey: true, shiftKey: true }))).toEqual({ kind: 'cycle', delta: 1 })
  })

  it('ignores plain keys, Esc, Alt combos and unshifted Enter', () => {
    expect(shortcutFor(k({ key: 'Escape' }))).toBeNull()
    expect(shortcutFor(k({ key: 'Escape', ctrlKey: true, shiftKey: true }))).toBeNull()
    expect(shortcutFor(k({ key: 'Enter', ctrlKey: true }))).toBeNull()
    expect(shortcutFor(k({ key: '2', ctrlKey: true, altKey: true }))).toBeNull()
    expect(shortcutFor(k({ key: 'c', ctrlKey: true }))).toBeNull()
  })
})

describe('useLayoutShortcuts', () => {
  const sessions = [makeSession('a'), makeSession('b'), makeSession('c')]
  let toggled = 0
  beforeEach(() => {
    toggled = 0
    useSessionStore.setState({ activeSessionId: 'a', layoutMode: 'grid', multiLayoutMode: 'grid', primarySessionId: null })
  })
  afterEach(() => { document.body.innerHTML = '' })

  const press = (init: KeyboardEventInit, target: EventTarget = window) => {
    const e = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
    target.dispatchEvent(e)
    return e
  }

  it('switches, cycles (wrapping) and toggles; stops the key reaching the terminal', () => {
    renderHook(() => useLayoutShortcuts(sessions, () => { toggled++ }))
    // Dispatch on an element (as xterm's textarea would receive it): the
    // capture-phase listener must stop it before element handlers run.
    const ta = document.createElement('textarea')
    document.body.appendChild(ta)
    let reached = false
    ta.addEventListener('keydown', () => { reached = true })

    const e = press({ key: '3', ctrlKey: true }, ta)
    expect(useSessionStore.getState().activeSessionId).toBe('c')
    expect(e.defaultPrevented).toBe(true)
    expect(reached).toBe(false)

    press({ key: '}', code: 'BracketRight', ctrlKey: true, shiftKey: true })
    expect(useSessionStore.getState().activeSessionId).toBe('a')
    press({ key: '{', code: 'BracketLeft', ctrlKey: true, shiftKey: true })
    expect(useSessionStore.getState().activeSessionId).toBe('c')

    press({ key: 'Enter', ctrlKey: true, shiftKey: true })
    expect(useSessionStore.getState().layoutMode).toBe('focus')
    press({ key: 'F', code: 'KeyF', ctrlKey: true, shiftKey: true })
    expect(toggled).toBe(1)
  })

  it('lets Ctrl+N through when there is no shell N', () => {
    renderHook(() => useLayoutShortcuts(sessions, () => {}))
    const e = press({ key: '5', ctrlKey: true })
    expect(e.defaultPrevented).toBe(false)
    expect(useSessionStore.getState().activeSessionId).toBe('a')
  })
})

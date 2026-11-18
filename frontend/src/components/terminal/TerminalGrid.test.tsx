import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { useEffect } from 'react'
import { useSessionStore } from '@/store/sessionStore'
import type { Session } from '@/types/session'

// Count mounts/unmounts: a real TerminalPane remount disposes xterm and
// reconnects the WebSocket, which is exactly what toggling must avoid.
const lifecycle = { mounts: 0, unmounts: 0 }
vi.mock('./TerminalPane', () => ({
  TerminalPane: ({ session, isActive }: { session: Session; isActive: boolean }) => {
    useEffect(() => {
      lifecycle.mounts++
      return () => { lifecycle.unmounts++ }
    }, [])
    return <div data-testid={`pane-${session.id}`} data-active={isActive} />
  },
}))

import { TerminalGrid } from './TerminalGrid'

const mk = (id: string) =>
  ({ id, name: id, image: 'bash', status: 'running', cols: 80, rows: 24, created_at: '', last_active_at: '' }) as Session

describe('TerminalGrid focus mode', () => {
  const sessions = [mk('a'), mk('b'), mk('c')]
  beforeEach(() => {
    lifecycle.mounts = 0
    lifecycle.unmounts = 0
    useSessionStore.setState({ activeSessionId: 'b' })
  })

  it('toggling grid ↔ focus keeps every pane mounted', () => {
    const { rerender } = render(<TerminalGrid sessions={sessions} isMobile={false} />)
    expect(lifecycle.mounts).toBe(3)
    rerender(<TerminalGrid sessions={sessions} isMobile={false} focus />)
    rerender(<TerminalGrid sessions={sessions} isMobile={false} />)
    expect(lifecycle.mounts).toBe(3)
    expect(lifecycle.unmounts).toBe(0)
  })

  it('shows only the active shell in focus mode and follows selection', () => {
    render(<TerminalGrid sessions={sessions} isMobile={false} focus />)
    const wrapper = (id: string) => screen.getByTestId(`pane-${id}`).parentElement!
    expect(wrapper('b').className).not.toContain('invisible')
    expect(wrapper('a').className).toContain('invisible')
    expect(wrapper('c').className).toContain('invisible')

    act(() => useSessionStore.getState().setActiveSession('c'))
    expect(wrapper('c').className).not.toContain('invisible')
    expect(wrapper('b').className).toContain('invisible')
    expect(screen.getByTestId('pane-c').dataset.active).toBe('true')
    expect(lifecycle.unmounts).toBe(0)
  })
})

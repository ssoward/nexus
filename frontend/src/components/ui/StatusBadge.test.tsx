import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'
import type { SessionStatus } from '@/types/session'

describe('StatusBadge', () => {
  it.each<[SessionStatus, string]>([
    ['running', 'running'],
    ['stopped', 'stopped'],
    ['pending', 'pending'],
    ['error', 'error'],
    ['recovery_pending', 'recovering'],
  ])('renders %s as "%s"', (status, label) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('applies the running color class', () => {
    render(<StatusBadge status="running" />)
    expect(screen.getByText('running').className).toContain('text-green-400')
  })

  it('falls back to the error style for an unknown status', () => {
    // @ts-expect-error — intentionally passing an invalid status
    render(<StatusBadge status="bogus" />)
    expect(screen.getByText('error')).toBeInTheDocument()
  })
})

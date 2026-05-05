import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { LoginForm } from './LoginForm'
import { useAuthStore } from '@/store/authStore'

// Mock the auth API module
vi.mock('@/api/auth', () => ({
  login: vi.fn(),
}))

// Capture window.location.href assignments
const locationRef = { href: '' }
Object.defineProperty(window, 'location', {
  value: locationRef,
  writable: true,
})

describe('LoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    locationRef.href = ''
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })

  it('renders username and password inputs', () => {
    render(<LoginForm />)
    expect(screen.getByRole('textbox')).toBeInTheDocument() // email
    expect(document.querySelector('input[type="password"]')).toBeInTheDocument()
  })

  it('shows error when submitting empty fields', async () => {
    render(<LoginForm />)
    await userEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
    expect(screen.getByText(/email and password are required/i)).toBeInTheDocument()
  })

  it('shows TOTP step when server returns needs_totp', async () => {
    const { login } = await import('@/api/auth')
    vi.mocked(login).mockResolvedValueOnce({ ok: false, needs_totp: true })

    const { container } = render(<LoginForm />)
    await userEvent.type(container.querySelector('input[autocomplete="email"]')!, 'alice@example.com')
    await userEvent.type(container.querySelector('input[autocomplete="current-password"]')!, 'secret123')
    await userEvent.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => {
      expect(screen.getByText(/authenticator code/i)).toBeInTheDocument()
    })
  })

  it('redirects to / on successful login', async () => {
    const { login } = await import('@/api/auth')
    vi.mocked(login).mockResolvedValueOnce({ ok: true, username: 'alice' })

    const { container } = render(<LoginForm />)
    await userEvent.type(container.querySelector('input[autocomplete="email"]')!, 'alice@example.com')
    await userEvent.type(container.querySelector('input[autocomplete="current-password"]')!, 'secret123')
    await userEvent.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => {
      expect(locationRef.href).toBe('/')
    })
  })

  it('shows generic error on invalid credentials (non-429)', async () => {
    const { login } = await import('@/api/auth')
    vi.mocked(login).mockRejectedValueOnce({ response: { status: 401 } })

    const { container } = render(<LoginForm />)
    await userEvent.type(container.querySelector('input[autocomplete="email"]')!, 'alice@example.com')
    await userEvent.type(container.querySelector('input[autocomplete="current-password"]')!, 'bad')
    await userEvent.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument()
    })
  })

  it('shows rate-limit error on 429', async () => {
    const { login } = await import('@/api/auth')
    vi.mocked(login).mockRejectedValueOnce({ response: { status: 429 } })

    const { container } = render(<LoginForm />)
    await userEvent.type(container.querySelector('input[autocomplete="email"]')!, 'alice@example.com')
    await userEvent.type(container.querySelector('input[autocomplete="current-password"]')!, 'pass')
    await userEvent.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => {
      expect(screen.getByText(/too many attempts/i)).toBeInTheDocument()
    })
  })

  it('back button returns to credentials step', async () => {
    const { login } = await import('@/api/auth')
    vi.mocked(login).mockResolvedValueOnce({ ok: false, needs_totp: true })

    const { container } = render(<LoginForm />)
    await userEvent.type(container.querySelector('input[autocomplete="email"]')!, 'alice@example.com')
    await userEvent.type(container.querySelector('input[autocomplete="current-password"]')!, 'secret123')
    await userEvent.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => screen.getByText(/authenticator code/i))
    await userEvent.click(screen.getByRole('button', { name: /back/i }))

    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument()
  })
})

import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuth } from './useAuth'
import { useAuthStore } from '@/store/authStore'
import * as authApi from '@/api/auth'

vi.mock('@/api/auth', () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}))

describe('useAuth', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
    vi.clearAllMocks()
  })

  it('sets user when getMe resolves', async () => {
    vi.mocked(authApi.getMe).mockResolvedValueOnce({ id: 1, username: 'alice' })

    const { result } = renderHook(() => useAuth())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.user).toEqual({ id: 1, username: 'alice' })
    expect(result.current.isAuthenticated).toBe(true)
  })

  it('sets user to null when getMe rejects', async () => {
    vi.mocked(authApi.getMe).mockRejectedValueOnce(new Error('Unauthorized'))

    const { result } = renderHook(() => useAuth())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.user).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
  })

  it('starts in loading state before getMe resolves', async () => {
    let resolve!: (value: { id: number; username: string }) => void
    vi.mocked(authApi.getMe).mockReturnValueOnce(
      new Promise((r) => { resolve = r }),
    )

    const { result } = renderHook(() => useAuth())
    expect(result.current.loading).toBe(true)

    // Clean up — resolve the pending promise
    resolve({ id: 1, username: 'alice' })
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it('logout calls api logout and clears user', async () => {
    vi.mocked(authApi.getMe).mockResolvedValueOnce({ id: 1, username: 'alice' })
    vi.mocked(authApi.logout).mockResolvedValueOnce(undefined)

    // Capture location redirect
    const locationRef = { href: '' }
    Object.defineProperty(window, 'location', { value: locationRef, writable: true })

    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.logout()
    })

    expect(authApi.logout).toHaveBeenCalledOnce()
    expect(useAuthStore.getState().user).toBeNull()
    expect(locationRef.href).toBe('/login')
  })
})

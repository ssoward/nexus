import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from './authStore'

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })

  it('has correct initial state', () => {
    const { user, isAuthenticated } = useAuthStore.getState()
    expect(user).toBeNull()
    expect(isAuthenticated).toBe(false)
  })

  it('setUser sets user and marks authenticated', () => {
    useAuthStore.getState().setUser({ id: 1, username: 'alice' })
    const { user, isAuthenticated } = useAuthStore.getState()
    expect(user).toEqual({ id: 1, username: 'alice' })
    expect(isAuthenticated).toBe(true)
  })

  it('setUser(null) clears user and marks unauthenticated', () => {
    useAuthStore.getState().setUser({ id: 1, username: 'alice' })
    useAuthStore.getState().setUser(null)
    const { user, isAuthenticated } = useAuthStore.getState()
    expect(user).toBeNull()
    expect(isAuthenticated).toBe(false)
  })

  it('isAuthenticated is false when user is null regardless of prior state', () => {
    useAuthStore.getState().setUser({ id: 99, username: 'bob' })
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    useAuthStore.getState().setUser(null)
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})

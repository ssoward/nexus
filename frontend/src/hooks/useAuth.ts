import { useEffect, useState } from 'react'
import { useAuthStore } from '@/store/authStore'
import { getMe, logout as apiLogout, refreshToken } from '@/api/auth'

// Refresh the cookie at 30-minute intervals — comfortably inside the 60-minute JWT TTL.
const REFRESH_INTERVAL_MS = 30 * 60 * 1000

export function useAuth() {
  const { user, isAuthenticated, setUser } = useAuthStore()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [setUser])

  // Silently refresh the token while the tab is open so active users
  // are never evicted by the 60-minute hard TTL.
  useEffect(() => {
    if (!isAuthenticated) return
    const id = setInterval(() => {
      refreshToken().catch(() => {
        // If refresh fails the user's session has genuinely expired;
        // the next API call will 401 and the interceptor will redirect to /login.
      })
    }, REFRESH_INTERVAL_MS)
    return () => clearInterval(id)
  }, [isAuthenticated])

  const logout = async () => {
    await apiLogout()
    setUser(null)
    window.location.href = '/login'
  }

  return { user, isAuthenticated, loading, logout }
}

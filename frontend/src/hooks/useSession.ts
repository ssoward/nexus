import { useCallback } from 'react'
import { useSessionStore } from '@/store/sessionStore'
import { listSessions, createSession, deleteSession as apiDeleteSession } from '@/api/sessions'
import type { CreateSessionRequest } from '@/types/session'

export function useSession() {
  const { sessions, setSessions, addSession, removeSession } = useSessionStore()

  const refresh = useCallback(async () => {
    const list = await listSessions()
    setSessions(list)
  }, [setSessions])

  const create = useCallback(
    async (req: CreateSessionRequest) => {
      const session = await createSession(req)
      addSession(session)
      return session
    },
    [addSession]
  )

  const remove = useCallback(
    async (id: string) => {
      await apiDeleteSession(id)
      removeSession(id)
    },
    [removeSession]
  )

  return { sessions, refresh, create, remove }
}

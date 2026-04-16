import client from './client'
import type { Session, CreateSessionRequest } from '@/types/session'

export async function listSessions(): Promise<Session[]> {
  const res = await client.get<Session[]>('/sessions')
  return res.data
}

export async function createSession(req: CreateSessionRequest): Promise<Session> {
  const res = await client.post<Session>('/sessions', req)
  return res.data
}

export async function deleteSession(sessionId: string): Promise<void> {
  await client.delete(`/sessions/${sessionId}`)
}

export async function resizeSession(sessionId: string, cols: number, rows: number): Promise<void> {
  await client.patch(`/sessions/${sessionId}/resize`, { cols, rows })
}

export async function restartSession(sessionId: string): Promise<Session> {
  const res = await client.post<Session>(`/sessions/${sessionId}/restart`)
  return res.data
}

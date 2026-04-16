import client from './client'

export interface SessionState {
  session_id: string
  name: string
  state: 'WORKING' | 'WAITING' | 'ASKING' | 'BUSY'
  idle_seconds: number
}

export interface BufferResponse {
  session_id: string
  lines: number
  buffer: string
}

export async function getAllSessionStates(): Promise<SessionState[]> {
  const res = await client.get<SessionState[]>('/orchestration/sessions/states')
  return res.data
}

export async function getSessionState(sessionId: string): Promise<SessionState> {
  const res = await client.get<SessionState>(`/orchestration/sessions/${sessionId}/state`)
  return res.data
}

export async function getSessionBuffer(sessionId: string, lines = 100): Promise<BufferResponse> {
  const res = await client.get<BufferResponse>(`/orchestration/sessions/${sessionId}/buffer`, {
    params: { lines },
  })
  return res.data
}

export async function sendSessionInput(sessionId: string, data: string): Promise<void> {
  await client.post(`/orchestration/sessions/${sessionId}/input`, { data })
}

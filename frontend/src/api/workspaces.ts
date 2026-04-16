import client from './client'
import type { Workspace, CreateWorkspaceRequest } from '@/types/workspace'

export async function listWorkspaces(): Promise<Workspace[]> {
  const res = await client.get<Workspace[]>('/workspaces')
  return res.data
}

export async function createWorkspace(req: CreateWorkspaceRequest): Promise<Workspace> {
  const res = await client.post<Workspace>('/workspaces', req)
  return res.data
}

export async function updateWorkspace(id: number, data: Partial<Workspace>): Promise<Workspace> {
  const res = await client.patch<Workspace>(`/workspaces/${id}`, data)
  return res.data
}

export async function deleteWorkspace(id: number): Promise<void> {
  await client.delete(`/workspaces/${id}`)
}

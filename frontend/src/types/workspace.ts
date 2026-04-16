export interface Workspace {
  id: number
  name: string
  color: string
  sort_order: number
  created_at: string
}

export interface CreateWorkspaceRequest {
  name: string
  color?: string
}

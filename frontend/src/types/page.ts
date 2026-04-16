export interface EmbeddedPage {
  id: number
  name: string
  url: string
  position: number
  created_at: string
}

export interface CreatePageRequest {
  name: string
  url: string
}

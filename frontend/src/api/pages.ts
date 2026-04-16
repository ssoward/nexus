import client from './client'
import type { EmbeddedPage, CreatePageRequest } from '@/types/page'

export async function listPages(): Promise<EmbeddedPage[]> {
  const res = await client.get<EmbeddedPage[]>('/pages')
  return res.data
}

export async function createPage(req: CreatePageRequest): Promise<EmbeddedPage> {
  const res = await client.post<EmbeddedPage>('/pages', req)
  return res.data
}

export async function updatePage(id: number, data: Partial<EmbeddedPage>): Promise<EmbeddedPage> {
  const res = await client.patch<EmbeddedPage>(`/pages/${id}`, data)
  return res.data
}

export async function deletePage(id: number): Promise<void> {
  await client.delete(`/pages/${id}`)
}

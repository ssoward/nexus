import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the shared axios client so we assert URL + payload without a network call.
vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}))

import client from './client'
import {
  listSessions,
  createSession,
  deleteSession,
  resizeSession,
  restartSession,
} from './sessions'

const mockClient = client as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
}

describe('sessions api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listSessions GETs /sessions and returns data', async () => {
    mockClient.get.mockResolvedValue({ data: [{ id: 'a' }] })
    const out = await listSessions()
    expect(mockClient.get).toHaveBeenCalledWith('/sessions')
    expect(out).toEqual([{ id: 'a' }])
  })

  it('createSession POSTs the request body', async () => {
    const req = { name: 'shell', image: 'bash', cols: 80, rows: 24 }
    mockClient.post.mockResolvedValue({ data: { id: 'new' } })
    const out = await createSession(req as never)
    expect(mockClient.post).toHaveBeenCalledWith('/sessions', req)
    expect(out).toEqual({ id: 'new' })
  })

  it('deleteSession DELETEs the id path', async () => {
    mockClient.delete.mockResolvedValue({})
    await deleteSession('abc')
    expect(mockClient.delete).toHaveBeenCalledWith('/sessions/abc')
  })

  it('resizeSession PATCHes cols/rows', async () => {
    mockClient.patch.mockResolvedValue({})
    await resizeSession('abc', 120, 40)
    expect(mockClient.patch).toHaveBeenCalledWith('/sessions/abc/resize', { cols: 120, rows: 40 })
  })

  it('restartSession POSTs the restart path', async () => {
    mockClient.post.mockResolvedValue({ data: { id: 'abc' } })
    const out = await restartSession('abc')
    expect(mockClient.post).toHaveBeenCalledWith('/sessions/abc/restart')
    expect(out).toEqual({ id: 'abc' })
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}))

import client from './client'
import { login, getWsToken, changePassword, deleteAccount, getMe } from './auth'

const mockClient = client as unknown as Record<'get' | 'post' | 'delete' | 'patch', ReturnType<typeof vi.fn>>

describe('auth api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('login posts form-encoded credentials to /auth/login', async () => {
    mockClient.post.mockResolvedValue({ data: { ok: true, username: 'a@b.co' } })
    const out = await login('a@b.co', 'pw', '123456')
    const [url, body] = mockClient.post.mock.calls[0]
    expect(url).toBe('/auth/login')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('username')).toBe('a@b.co')
    expect(body.get('password')).toBe('pw')
    expect(body.get('totp_code')).toBe('123456')
    expect(out.ok).toBe(true)
  })

  it('login omits totp_code when not provided', async () => {
    mockClient.post.mockResolvedValue({ data: { ok: false } })
    await login('a@b.co', 'pw')
    const body = mockClient.post.mock.calls[0][1] as FormData
    expect(body.get('totp_code')).toBeNull()
  })

  it('getWsToken posts session_id and returns the token string', async () => {
    mockClient.post.mockResolvedValue({ data: { ws_token: 'tok-123' } })
    const out = await getWsToken('sess-1')
    const body = mockClient.post.mock.calls[0][1] as FormData
    expect(mockClient.post.mock.calls[0][0]).toBe('/auth/ws-token')
    expect(body.get('session_id')).toBe('sess-1')
    expect(out).toBe('tok-123')
  })

  it('changePassword posts snake_case JSON body', async () => {
    mockClient.post.mockResolvedValue({ data: {} })
    await changePassword('old', 'new')
    expect(mockClient.post).toHaveBeenCalledWith('/auth/change-password', {
      current_password: 'old',
      new_password: 'new',
    })
  })

  it('deleteAccount sends password in the request data', async () => {
    mockClient.delete.mockResolvedValue({})
    await deleteAccount('pw')
    expect(mockClient.delete).toHaveBeenCalledWith('/auth/account', { data: { password: 'pw' } })
  })

  it('getMe GETs /auth/me', async () => {
    mockClient.get.mockResolvedValue({ data: { id: 1, username: 'a@b.co' } })
    const out = await getMe()
    expect(mockClient.get).toHaveBeenCalledWith('/auth/me')
    expect(out).toMatchObject({ id: 1 })
  })
})

import client from './client'
import type { LoginResponse, TotpSetupResponse, MfaSetupResponse, RegisterResponse, User, WsTokenResponse } from '@/types/auth'

export async function login(
  username: string,
  password: string,
  totpCode?: string,
): Promise<LoginResponse> {
  const form = new FormData()
  form.append('username', username)
  form.append('password', password)
  if (totpCode) form.append('totp_code', totpCode)
  const res = await client.post<LoginResponse>('/auth/login', form)
  return res.data
}

export async function logout(): Promise<void> {
  await client.post('/auth/logout')
}

export async function getMe(): Promise<User> {
  const res = await client.get<User>('/auth/me')
  return res.data
}

export async function register(
  email: string,
  password: string,
): Promise<RegisterResponse> {
  const res = await client.post<RegisterResponse>('/auth/create-user', { username: email, password })
  return res.data
}

export async function setupMfa(
  email: string,
  password: string,
  method: 'totp' | 'email_otp',
): Promise<MfaSetupResponse> {
  const form = new FormData()
  form.append('username', email)
  form.append('password', password)
  form.append('method', method)
  const res = await client.post<MfaSetupResponse>('/auth/setup-mfa', form)
  return res.data
}

export async function resendOtp(
  email: string,
  password: string,
): Promise<{ ok: boolean; message: string }> {
  const form = new FormData()
  form.append('username', email)
  form.append('password', password)
  const res = await client.post('/auth/resend-otp', form)
  return res.data as { ok: boolean; message: string }
}

export async function switchMfa(
  email: string,
  password: string,
  method: 'totp' | 'email_otp',
): Promise<{ method: string; needs_setup: boolean; provisioning_uri?: string; qr_code_base64?: string }> {
  const form = new FormData()
  form.append('username', email)
  form.append('password', password)
  form.append('method', method)
  const res = await client.post('/auth/switch-mfa', form)
  return res.data as { method: string; needs_setup: boolean; provisioning_uri?: string; qr_code_base64?: string }
}

export async function bootstrapTotp(
  username: string,
  password: string,
): Promise<TotpSetupResponse> {
  const form = new FormData()
  form.append('username', username)
  form.append('password', password)
  const res = await client.post<TotpSetupResponse>('/auth/bootstrap-totp', form)
  return res.data
}

export async function refreshToken(): Promise<void> {
  await client.post('/auth/refresh')
}

export async function getWsToken(sessionId: string): Promise<string> {
  const res = await client.get<WsTokenResponse>('/auth/ws-token', {
    params: { session_id: sessionId },
  })
  return res.data.ws_token
}

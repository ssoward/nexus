import client from './client'
import type { LoginResponse, TotpSetupResponse, MfaSetupResponse, RegisterResponse, User, WsTokenResponse, PasskeyCredential } from '@/types/auth'
import type { PublicKeyCredentialCreationOptionsJSON, PublicKeyCredentialRequestOptionsJSON, RegistrationResponseJSON, AuthenticationResponseJSON } from '@simplewebauthn/browser'

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
  setupToken?: string,
): Promise<RegisterResponse> {
  const res = await client.post<RegisterResponse>('/auth/create-user', {
    username: email,
    password,
    setup_token: setupToken ?? '',
  })
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

export async function requestRecovery(username: string): Promise<{ ok: boolean; message: string }> {
  const form = new FormData()
  form.append('username', username)
  const res = await client.post('/auth/recovery/request', form)
  return res.data as { ok: boolean; message: string }
}

export async function resetRecovery(token: string): Promise<{ ok: boolean }> {
  const form = new FormData()
  form.append('token', token)
  const res = await client.post('/auth/recovery/reset', form)
  return res.data as { ok: boolean }
}

export async function refreshToken(): Promise<void> {
  await client.post('/auth/refresh')
}

export async function getWsToken(sessionId: string): Promise<string> {
  const form = new FormData()
  form.append('session_id', sessionId)
  const res = await client.post<WsTokenResponse>('/auth/ws-token', form)
  return res.data.ws_token
}

export async function setupPasskeyBegin(
  email: string,
  password: string,
): Promise<PublicKeyCredentialCreationOptionsJSON> {
  const res = await client.post('/auth/passkey/setup/begin', { username: email, password })
  return res.data
}

export async function setupPasskeyComplete(
  email: string,
  password: string,
  credential: RegistrationResponseJSON,
): Promise<LoginResponse> {
  const res = await client.post<LoginResponse>('/auth/passkey/setup/complete', {
    username: email,
    password,
    credential,
  })
  return res.data
}

export async function beginPasskeyAuthentication(
  username: string,
): Promise<PublicKeyCredentialRequestOptionsJSON> {
  const res = await client.post('/auth/passkey/authenticate/begin', { username })
  return res.data
}

export async function completePasskeyAuthentication(
  username: string,
  credential: AuthenticationResponseJSON,
): Promise<LoginResponse> {
  const res = await client.post<LoginResponse>('/auth/passkey/authenticate/complete', {
    username,
    credential,
  })
  return res.data
}

export async function listPasskeyCredentials(): Promise<PasskeyCredential[]> {
  const res = await client.get<PasskeyCredential[]>('/auth/passkey/credentials')
  return res.data
}

export async function deletePasskeyCredential(id: number): Promise<void> {
  await client.delete(`/auth/passkey/credentials/${id}`)
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await client.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword })
}

export async function changeEmail(currentPassword: string, newEmail: string): Promise<{ ok: boolean; username: string }> {
  const res = await client.patch<{ ok: boolean; username: string }>('/auth/change-email', {
    current_password: currentPassword,
    new_email: newEmail,
  })
  return res.data
}

export async function deleteAccount(password: string): Promise<void> {
  await client.delete('/auth/account', { data: { password } })
}

export async function registerPasskeyBegin(): Promise<PublicKeyCredentialCreationOptionsJSON> {
  const res = await client.post<PublicKeyCredentialCreationOptionsJSON>('/auth/passkey/register/begin')
  return res.data
}

export async function registerPasskeyComplete(
  credential: RegistrationResponseJSON,
  name?: string,
): Promise<{ ok: boolean }> {
  const res = await client.post<{ ok: boolean }>('/auth/passkey/register/complete', { credential, name: name ?? '' })
  return res.data
}

export async function beginPasswordlessAuth(): Promise<PublicKeyCredentialRequestOptionsJSON & { challenge_token: string }> {
  const res = await client.post<PublicKeyCredentialRequestOptionsJSON & { challenge_token: string }>('/auth/passkey/login/begin')
  return res.data
}

export async function completePasswordlessAuth(
  credential: AuthenticationResponseJSON,
  challengeToken: string,
): Promise<LoginResponse> {
  const res = await client.post<LoginResponse>('/auth/passkey/login/complete', {
    credential,
    challenge_token: challengeToken,
  })
  return res.data
}

// ── Step-up (re-verify a second factor inside the current session) ────────────
//
// Account-changing endpoints answer 403 {detail:{code:'step_up_required', methods}}
// when the session's second factor was verified more than a few minutes ago.
// The client then verifies one of `methods` here; the server re-issues the cookie
// and the original request can be retried.

export type StepUpMethod = 'passkey' | 'totp' | 'email_otp'

export interface StepUpRequiredDetail {
  code: 'step_up_required'
  methods: StepUpMethod[]
  max_age_seconds: number
}

/** Returns the step-up detail if `err` is a 403 step_up_required, else null. */
export function asStepUpRequired(err: unknown): StepUpRequiredDetail | null {
  const resp = (err as { response?: { status?: number; data?: { detail?: unknown } } }).response
  const detail = resp?.data?.detail as Partial<StepUpRequiredDetail> | undefined
  if (resp?.status === 403 && detail && detail.code === 'step_up_required') {
    return { code: 'step_up_required', methods: detail.methods ?? [], max_age_seconds: detail.max_age_seconds ?? 300 }
  }
  return null
}

export async function getStepUpMethods(): Promise<StepUpMethod[]> {
  const res = await client.get<{ methods: StepUpMethod[] }>('/auth/step-up/methods')
  return res.data.methods
}

export async function stepUpSendEmailCode(): Promise<void> {
  await client.post('/auth/step-up/email/send')
}

export async function stepUpPasskeyBegin(): Promise<PublicKeyCredentialRequestOptionsJSON> {
  const res = await client.post<PublicKeyCredentialRequestOptionsJSON>('/auth/step-up/passkey/begin')
  return res.data
}

export async function stepUp(
  method: StepUpMethod,
  code?: string,
  credential?: AuthenticationResponseJSON,
): Promise<void> {
  await client.post('/auth/step-up', { method, code: code ?? '', credential: credential ?? null })
}

export async function enableEmailOtp(): Promise<void> {
  await client.post('/auth/email-otp/enable')
}

export async function disableEmailOtp(): Promise<void> {
  await client.post('/auth/email-otp/disable')
}

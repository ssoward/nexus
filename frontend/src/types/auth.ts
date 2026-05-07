export interface User {
  id: number
  username: string
  mfa_method?: string | null
  has_totp?: boolean
  has_passkey?: boolean
  passkey_count?: number
}

export interface LoginRequest {
  username: string
  password: string
  totp_code: string
}

export interface LoginResponse {
  ok: boolean
  username?: string
  needs_totp?: boolean
  needs_mfa_setup?: boolean
  needs_email_otp?: boolean
  needs_passkey?: boolean
  available_methods?: string[]
}

export interface PasskeyCredential {
  id: number
  name: string | null
  aaguid: string | null
  created_at: string
  last_used_at: string | null
}

export interface TotpSetupResponse {
  provisioning_uri: string
  qr_code_base64: string
}

export interface MfaSetupResponse {
  method: 'totp' | 'email_otp'
  provisioning_uri?: string
  qr_code_base64?: string
  message?: string
}

export interface RegisterResponse {
  ok: boolean
  message: string
}

export interface WsTokenResponse {
  ws_token: string
}

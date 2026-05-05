import { useState } from 'react'
import { startRegistration, startAuthentication } from '@simplewebauthn/browser'
import { login, register, setupMfa, resendOtp, switchMfa, requestRecovery, setupPasskeyBegin, setupPasskeyComplete, beginPasskeyAuthentication, completePasskeyAuthentication, beginPasswordlessAuth, completePasswordlessAuth } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import type { User } from '@/types/auth'

type Step =
  | 'credentials'
  | 'register'
  | 'mfa_choice'
  | 'totp_setup'
  | 'email_otp_setup'
  | 'totp'
  | 'email_otp'
  | 'passkey'
  | 'passkey_setup'
  | 'recovery_sent'

export function LoginForm() {
  const [step, setStep] = useState<Step>('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [code, setCode] = useState('')
  const [qrCode, setQrCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setUser } = useAuthStore()

  const resetCode = () => { setCode(''); setError('') }

  // ── Credentials step (sign in) ─────────────────────────────────────
  const handleCredentials = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) { setError('Email and password are required'); return }
    setLoading(true); setError('')
    try {
      const res = await login(email, password)
      if (res.needs_mfa_setup) {
        setStep('mfa_choice')
      } else if (res.needs_totp) {
        setStep('totp')
      } else if (res.needs_email_otp) {
        setStep('email_otp')
      } else if (res.needs_passkey) {
        setStep('passkey')
      } else if (res.ok) {
        setUser({ id: 0, username: res.username ?? email } as User)
        window.location.href = '/'
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status: number } }).response?.status
      setError(status === 429 ? 'Too many attempts. Wait a minute.' : 'Invalid credentials or account locked.')
    } finally { setLoading(false) }
  }

  // ── Register step ──────────────────────────────────────────────────
  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) { setError('Email and password are required'); return }
    if (password !== confirmPassword) { setError('Passwords do not match'); return }
    setLoading(true); setError('')
    try {
      await register(email, password)
      setStep('mfa_choice')
    } catch (err: unknown) {
      const resp = (err as { response?: { status: number; data?: { detail?: unknown } } }).response
      if (resp?.status === 409) setError('An account with this email already exists.')
      else if (resp?.status === 422) {
        // Pydantic returns detail as an array of {msg} objects
        const detail = resp.data?.detail
        if (Array.isArray(detail)) setError(detail.map((d: { msg?: string }) => d.msg ?? '').join('. '))
        else if (typeof detail === 'string') setError(detail)
        else setError('Invalid input.')
      }
      else setError('Registration failed.')
    } finally { setLoading(false) }
  }

  // ── MFA choice ─────────────────────────────────────────────────────
  const handleMfaChoice = async (method: 'totp' | 'email_otp' | 'passkey') => {
    if (method === 'passkey') {
      setStep('passkey_setup')
      return
    }
    setLoading(true); setError('')
    try {
      const res = await setupMfa(email, password, method)
      if (res.method === 'totp' && res.qr_code_base64) {
        setQrCode(res.qr_code_base64)
        setStep('totp_setup')
      } else {
        setStep('email_otp_setup')
      }
    } catch {
      setError('Failed to set up MFA. Try again.')
    } finally { setLoading(false) }
  }

  // ── Passkey setup (first-time MFA) ─────────────────────────────────
  const handlePasskeySetup = async () => {
    setLoading(true); setError('')
    try {
      const options = await setupPasskeyBegin(email, password)
      const credential = await startRegistration({ optionsJSON: options })
      const res = await setupPasskeyComplete(email, password, credential)
      if (res.ok) {
        setUser({ id: 0, username: res.username ?? email } as User)
        window.location.href = '/'
      }
    } catch (err: unknown) {
      const name = (err as { name?: string }).name
      if (name === 'NotAllowedError') setError('Biometric cancelled or not allowed.')
      else setError('Passkey setup failed. Try again.')
    } finally { setLoading(false) }
  }

  // ── Passkey authentication (returning user) ────────────────────────
  const handlePasskeyAuthentication = async () => {
    setLoading(true); setError('')
    try {
      const options = await beginPasskeyAuthentication(email)
      const credential = await startAuthentication({ optionsJSON: options })
      const res = await completePasskeyAuthentication(email, credential)
      if (res.ok) {
        setUser({ id: 0, username: res.username ?? email } as User)
        window.location.href = '/'
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status: number } }).response?.status
      const name = (err as { name?: string }).name
      if (name === 'NotAllowedError') setError('Biometric cancelled or not allowed.')
      else setError(status === 429 ? 'Too many attempts. Wait a minute.' : 'Authentication failed. Try again.')
    } finally { setLoading(false) }
  }

  // ── Passwordless / biometric login (no username or password) ────────
  const handlePasswordlessLogin = async () => {
    setLoading(true); setError('')
    try {
      const beginData = await beginPasswordlessAuth()
      const { challenge_token, ...optionsJSON } = beginData
      const credential = await startAuthentication({ optionsJSON: optionsJSON as Parameters<typeof startAuthentication>[0]['optionsJSON'] })
      const res = await completePasswordlessAuth(credential, challenge_token)
      if (res.ok) {
        setUser({ id: 0, username: res.username ?? '' } as User)
        window.location.href = '/'
      }
    } catch (err: unknown) {
      const name = (err as { name?: string }).name
      if (name === 'NotAllowedError') setError('Biometric cancelled or not available.')
      else if (name === 'NotSupportedError') setError('No passkeys available on this device.')
      else setError('Passkey sign-in failed. Try again.')
    } finally { setLoading(false) }
  }

  // ── TOTP / Email OTP verification ──────────────────────────────────
  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault()
    if (code.length !== 6) { setError('Enter the 6-digit code'); return }
    setLoading(true); setError('')
    try {
      const res = await login(email, password, code)
      if (res.ok) {
        setUser({ id: 0, username: res.username ?? email } as User)
        window.location.href = '/'
      } else {
        setError('Invalid code. Try again.')
        setCode('')
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status: number } }).response?.status
      setError(status === 429 ? 'Too many attempts. Wait a minute.' : 'Invalid code or account locked.')
      setCode('')
    } finally { setLoading(false) }
  }

  // ── Resend email OTP ───────────────────────────────────────────────
  const [showPassword, setShowPassword] = useState(false)
  const [resendMsg, setResendMsg] = useState('')
  const handleResend = async () => {
    setLoading(true); setError(''); setResendMsg('')
    try {
      await resendOtp(email, password)
      setResendMsg('New code sent — check your email.')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string }; status?: number } }).response
      setError(detail?.status === 429 ? 'Wait before resending.' : (detail?.data?.detail ?? 'Failed to resend code.'))
    } finally { setLoading(false) }
  }

  const handleSwitchMfa = async (method: 'totp' | 'email_otp') => {
    setLoading(true); setError(''); setResendMsg(''); resetCode()
    try {
      const res = await switchMfa(email, password, method)
      if (res.method === 'totp') {
        if (res.needs_setup && res.qr_code_base64) {
          setQrCode(res.qr_code_base64)
          setStep('totp_setup')
        } else {
          setStep('totp')
        }
      } else {
        setStep('email_otp')
      }
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail ?? 'Failed to switch verification method.')
    } finally { setLoading(false) }
  }

  // ── Account recovery ──────────────────────────────────────────────
  const handleRequestRecovery = async () => {
    setLoading(true); setError('')
    try {
      await requestRecovery(email)
      setStep('recovery_sent')
    } catch {
      setError('Failed to send recovery email. Try again.')
    } finally { setLoading(false) }
  }

  const codeInput = (
    <input
      type="text"
      inputMode="numeric"
      pattern="[0-9]{6}"
      maxLength={6}
      value={code}
      onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
      autoFocus
      autoComplete="one-time-code"
      placeholder="000000"
      className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active tracking-widest text-center"
    />
  )

  const backButton = (target: Step = 'credentials') => (
    <button type="button" onClick={() => { setStep(target); resetCode() }}
      className="w-full py-1 text-xs text-terminal-fg/40 font-mono hover:text-terminal-fg/70">
      ← Back
    </button>
  )

  return (
    <div className="min-h-screen flex items-center justify-center bg-terminal-bg">
      <div className="w-full max-w-sm bg-[#161b22] border border-terminal-border rounded-lg p-8">
        <h1 className="text-2xl font-mono font-bold text-terminal-fg mb-1">Nexus</h1>
        <p className="text-xs text-terminal-fg/40 font-mono mb-6">Terminal Gateway</p>

        {/* ── Sign In ──────────────────────────────────────────────── */}
        {step === 'credentials' && (
          <div className="space-y-4">
            <button type="button" onClick={handlePasswordlessLogin} disabled={loading}
              className="w-full py-2.5 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50 flex items-center justify-center gap-2">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2zm3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/>
              </svg>
              {loading ? 'Waiting for biometric...' : 'Sign in with Passkey'}
            </button>
            <div className="relative flex items-center">
              <div className="flex-grow border-t border-terminal-border/30" />
              <span className="mx-2 text-[10px] font-mono text-terminal-fg/25">or sign in with password</span>
              <div className="flex-grow border-t border-terminal-border/30" />
            </div>
            <form onSubmit={handleCredentials} className="space-y-3">
              <div>
                <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active" />
              </div>
              <div>
                <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active" />
              </div>
              {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
              <button type="submit" disabled={loading}
                className="w-full py-2 rounded border border-terminal-border text-terminal-fg/80 font-mono text-sm hover:border-terminal-active hover:text-terminal-fg disabled:opacity-50">
                {loading ? 'Checking...' : 'Sign In'}
              </button>
            </form>
            <button type="button" onClick={() => { setStep('register'); setError('') }}
              className="w-full py-1 text-xs text-terminal-active font-mono hover:underline">
              Create an account
            </button>
          </div>
        )}

        {/* ── Register ─────────────────────────────────────────────── */}
        {step === 'register' && (
          <form onSubmit={handleRegister} className="space-y-4">
            <p className="text-xs font-mono text-terminal-fg/60 mb-2">Create a new account</p>
            <div>
              <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                autoFocus autoComplete="email"
                className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active" />
            </div>
            <div>
              <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Password</label>
              <div className="relative">
                <input type={showPassword ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 pr-10 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active" />
                <button type="button" onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-terminal-fg/30 hover:text-terminal-fg/60 p-1"
                  tabIndex={-1} aria-label={showPassword ? 'Hide password' : 'Show password'}>
                  {showPassword ? (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M13.359 11.238C15.06 9.72 16 8 16 8s-3-5.5-8-5.5a7 7 0 0 0-2.79.588l.77.771A6 6 0 0 1 8 3.5c2.12 0 3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8a13 13 0 0 1-1.357 1.854l.888.884zM2.64 4.762A13 13 0 0 0 1.172 8a13 13 0 0 0 1.66 2.043C4.12 11.332 5.88 12.5 8 12.5a6 6 0 0 0 1.938-.318l.79.79A7 7 0 0 1 8 13.5C3 13.5 0 8 0 8s1.065-1.882 2.64-3.238zM3.5 5.379l1.141 1.14A3.5 3.5 0 0 0 9.48 11.36l1.149 1.15A4.5 4.5 0 0 1 3.5 5.38zM6.52 4.64l1.149 1.15a3.5 3.5 0 0 1 3.69 3.69l1.141 1.14A4.5 4.5 0 0 0 6.52 4.641z"/>
                      <path d="M14.854 14.146a.5.5 0 0 1-.708 0L1.146 1.146a.5.5 0 1 1 .708-.708l13 13a.5.5 0 0 1 0 .708z"/>
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8zM1.173 8a13 13 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5s3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8a13 13 0 0 1-1.66 2.043C11.88 11.332 10.12 12.5 8 12.5s-3.879-1.168-5.168-2.457A13 13 0 0 1 1.172 8z"/>
                      <path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0z"/>
                    </svg>
                  )}
                </button>
              </div>
              <p className="text-[10px] font-mono text-terminal-fg/30 mt-1">16+ chars, upper, lower, digit, special</p>
            </div>
            <div>
              <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Confirm Password</label>
              <div className="relative">
                <input type={showPassword ? 'text' : 'password'} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 pr-10 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active" />
              </div>
            </div>
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button type="submit" disabled={loading}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50">
              {loading ? 'Creating...' : 'Create Account'}
            </button>
            {backButton()}
          </form>
        )}

        {/* ── MFA Choice ───────────────────────────────────────────── */}
        {step === 'mfa_choice' && (
          <div className="space-y-4">
            <p className="text-xs font-mono text-terminal-fg/80">Choose your verification method</p>
            <p className="text-[10px] font-mono text-terminal-fg/40">This secures your account with two-factor authentication.</p>
            <button onClick={() => handleMfaChoice('totp')} disabled={loading}
              className="w-full py-3 rounded border border-terminal-border hover:border-terminal-active text-left px-4 transition-colors">
              <span className="text-sm font-mono text-terminal-fg">Authenticator App</span>
              <p className="text-[10px] font-mono text-terminal-fg/40 mt-0.5">Use Google Authenticator, Authy, or 1Password</p>
            </button>
            <button onClick={() => handleMfaChoice('email_otp')} disabled={loading}
              className="w-full py-3 rounded border border-terminal-border hover:border-terminal-active text-left px-4 transition-colors">
              <span className="text-sm font-mono text-terminal-fg">Email Code</span>
              <p className="text-[10px] font-mono text-terminal-fg/40 mt-0.5">Receive a 6-digit code at {email || 'your email'}</p>
            </button>
            <button onClick={() => handleMfaChoice('passkey')} disabled={loading}
              className="w-full py-3 rounded border border-terminal-border hover:border-terminal-active text-left px-4 transition-colors">
              <span className="text-sm font-mono text-terminal-fg">Passkey / Biometrics</span>
              <p className="text-[10px] font-mono text-terminal-fg/40 mt-0.5">Use Face ID, Touch ID, or a hardware security key</p>
            </button>
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            {backButton()}
          </div>
        )}

        {/* ── TOTP Setup (QR scan) ─────────────────────────────────── */}
        {step === 'totp_setup' && (
          <form onSubmit={handleVerifyCode} className="space-y-4">
            <p className="text-xs font-mono text-terminal-fg/80 mb-1">Set up your authenticator app</p>
            <p className="text-xs font-mono text-terminal-fg/50 mb-3">
              Scan this QR code with your authenticator app, then enter the 6-digit code to confirm.
            </p>
            {qrCode && (
              <div className="flex justify-center mb-4">
                <img src={`data:image/png;base64,${qrCode}`} alt="QR code" className="w-40 h-40 rounded border border-terminal-border" />
              </div>
            )}
            <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Authenticator Code</label>
            {codeInput}
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button type="submit" disabled={loading || code.length !== 6}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50">
              {loading ? 'Verifying...' : 'Activate & Sign In'}
            </button>
            {backButton('mfa_choice')}
          </form>
        )}

        {/* ── Email OTP Setup (first-time confirmation) ────────────── */}
        {step === 'email_otp_setup' && (
          <form onSubmit={handleVerifyCode} className="space-y-4">
            <p className="text-xs font-mono text-terminal-fg/80 mb-1">Check your email</p>
            <p className="text-xs font-mono text-terminal-fg/50 mb-3">
              We sent a 6-digit code to <span className="text-terminal-fg">{email}</span>. Enter it below to activate your account.
            </p>
            <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Verification Code</label>
            {codeInput}
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button type="submit" disabled={loading || code.length !== 6}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50">
              {loading ? 'Verifying...' : 'Verify & Sign In'}
            </button>
            {resendMsg && <p className="text-xs text-green-400 font-mono">{resendMsg}</p>}
            <button type="button" onClick={handleResend} disabled={loading}
              className="w-full py-1 text-xs text-terminal-active font-mono hover:underline disabled:opacity-50">
              Resend code
            </button>
            {backButton('mfa_choice')}
          </form>
        )}

        {/* ── TOTP (returning user) ────────────────────────────────── */}
        {step === 'totp' && (
          <form onSubmit={handleVerifyCode} className="space-y-4">
            <p className="text-xs text-terminal-fg/60 font-mono mb-3">
              Enter the 6-digit code from your authenticator app.
            </p>
            <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Authenticator Code</label>
            {codeInput}
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button type="submit" disabled={loading || code.length !== 6}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50">
              {loading ? 'Verifying...' : 'Sign In'}
            </button>
            <button type="button" onClick={() => handleSwitchMfa('email_otp')} disabled={loading}
              className="w-full py-1 text-xs text-terminal-fg/40 font-mono hover:text-terminal-active">
              Use email code instead
            </button>
            <button type="button" onClick={handleRequestRecovery} disabled={loading}
              className="w-full py-1 text-xs text-terminal-fg/30 font-mono hover:text-terminal-fg/60">
              Lost access to authenticator?
            </button>
            {backButton()}
          </form>
        )}

        {/* ── Passkey authentication (returning user) ──────────────── */}
        {step === 'passkey' && (
          <div className="space-y-4">
            <p className="text-xs font-mono text-terminal-fg/80">Biometric / Security Key</p>
            <p className="text-xs font-mono text-terminal-fg/50">
              Use your registered passkey to sign in.
            </p>
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button type="button" onClick={handlePasskeyAuthentication} disabled={loading}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50">
              {loading ? 'Waiting for biometric...' : 'Use Passkey'}
            </button>
            <button type="button" onClick={handleRequestRecovery} disabled={loading || !email}
              className="w-full py-1 text-xs text-terminal-fg/30 font-mono hover:text-terminal-fg/60 disabled:opacity-40">
              No passkey on this device? Send recovery link
            </button>
            {backButton()}
          </div>
        )}

        {/* ── Passkey setup (first-time MFA) ───────────────────────── */}
        {step === 'passkey_setup' && (
          <div className="space-y-4">
            <p className="text-xs font-mono text-terminal-fg/80">Set up Passkey</p>
            <p className="text-xs font-mono text-terminal-fg/50">
              Register a biometric or hardware security key for fast, secure sign-in.
            </p>
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button type="button" onClick={handlePasskeySetup} disabled={loading}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50">
              {loading ? 'Setting up...' : 'Register Biometric / Security Key'}
            </button>
            {backButton('mfa_choice')}
          </div>
        )}

        {/* ── Recovery sent ────────────────────────────────────────── */}
        {step === 'recovery_sent' && (
          <div className="space-y-4">
            <p className="text-sm font-mono text-green-400">Recovery email sent</p>
            <p className="text-xs font-mono text-terminal-fg/60">
              If <span className="text-terminal-fg">{email}</span> has an account, a reset link
              has been sent. Check your inbox and click the link to clear your MFA — it expires
              in 15 minutes.
            </p>
            <p className="text-xs font-mono text-terminal-fg/40">
              After clicking the link you'll be prompted to set up a new verification method on your next login.
            </p>
            {backButton()}
          </div>
        )}

        {/* ── Email OTP (returning user) ───────────────────────────── */}
        {step === 'email_otp' && (
          <form onSubmit={handleVerifyCode} className="space-y-4">
            <p className="text-xs font-mono text-terminal-fg/60 mb-3">
              We sent a 6-digit code to <span className="text-terminal-fg">{email}</span>.
            </p>
            <label className="block text-xs font-mono text-terminal-fg/60 mb-1">Verification Code</label>
            {codeInput}
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button type="submit" disabled={loading || code.length !== 6}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm hover:bg-blue-600 disabled:opacity-50">
              {loading ? 'Verifying...' : 'Sign In'}
            </button>
            {resendMsg && <p className="text-xs text-green-400 font-mono">{resendMsg}</p>}
            <button type="button" onClick={handleResend} disabled={loading}
              className="w-full py-1 text-xs text-terminal-active font-mono hover:underline disabled:opacity-50">
              Resend code
            </button>
            <button type="button" onClick={() => handleSwitchMfa('totp')} disabled={loading}
              className="w-full py-1 text-xs text-terminal-fg/40 font-mono hover:text-terminal-active">
              Use authenticator app instead
            </button>
            {backButton()}
          </form>
        )}
      </div>
    </div>
  )
}

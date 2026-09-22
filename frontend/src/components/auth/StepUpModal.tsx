// Step-up verification: re-prove a second factor before an account change.
//
// Shown when an API call answers 403 step_up_required. The user picks one of the
// factors the server listed (passkey, authenticator code, or e-mail code); on
// success the server has re-issued the session cookie with a fresh mfa_time and
// the caller retries the original action.
import { useEffect, useState } from 'react'
import { startAuthentication } from '@simplewebauthn/browser'
import {
  stepUp,
  stepUpPasskeyBegin,
  stepUpSendEmailCode,
  type StepUpMethod,
} from '@/api/auth'

interface Props {
  methods: StepUpMethod[]
  /** What the user was trying to do, e.g. "change your password". */
  purpose?: string
  onSuccess: () => void
  onCancel: () => void
}

const LABELS: Record<StepUpMethod, string> = {
  passkey: 'Passkey / Face ID / Touch ID',
  totp: 'Authenticator app code',
  email_otp: 'E-mail code',
}

export function StepUpModal({ methods, purpose, onSuccess, onCancel }: Props) {
  const [method, setMethod] = useState<StepUpMethod | null>(methods.length === 1 ? methods[0] : null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [emailSent, setEmailSent] = useState(false)

  const fail = (msg: string) => { setError(msg); setBusy(false) }

  const runPasskey = async () => {
    setBusy(true); setError('')
    try {
      const options = await stepUpPasskeyBegin()
      const credential = await startAuthentication({ optionsJSON: options })
      await stepUp('passkey', undefined, credential)
      onSuccess()
    } catch (err: unknown) {
      const name = (err as { name?: string }).name
      if (name === 'NotAllowedError') fail('Biometric cancelled or not allowed.')
      else fail('Passkey verification failed. Try again.')
    }
  }

  const sendEmail = async () => {
    setBusy(true); setError('')
    try {
      await stepUpSendEmailCode()
      setEmailSent(true)
      setBusy(false)
    } catch {
      fail('Could not send the e-mail code. Try again.')
    }
  }

  const submitCode = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!method || !code.trim()) return
    setBusy(true); setError('')
    try {
      await stepUp(method, code.trim())
      onSuccess()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 429) fail('Too many attempts. Wait a minute.')
      else fail('Incorrect code. Try again.')
    }
  }

  // Passkey needs no typed input: start it as soon as it is the chosen method.
  useEffect(() => {
    if (method === 'passkey') void runPasskey()
    if (method === 'email_otp' && !emailSent) void sendEmail()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [method])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="stepup-title"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-sm rounded-lg border border-terminal-border bg-[#161b22] p-5 space-y-4">
        <div>
          <h2 id="stepup-title" className="text-sm font-mono font-bold text-terminal-fg">Confirm it&apos;s you</h2>
          <p className="text-xs font-mono text-terminal-fg/50 mt-1">
            Verify your second factor to {purpose ?? 'make this change'}.
          </p>
        </div>

        {methods.length === 0 && (
          <p className="text-xs font-mono text-red-400">
            No verification method is enrolled on this account. Sign out and complete MFA setup first.
          </p>
        )}

        {method === null && methods.length > 1 && (
          <div className="space-y-2">
            {methods.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMethod(m)}
                className="w-full py-2.5 px-3 rounded border border-terminal-border text-left text-xs font-mono text-terminal-fg hover:border-terminal-active"
              >
                {LABELS[m]}
              </button>
            ))}
          </div>
        )}

        {method === 'passkey' && (
          <p className="text-xs font-mono text-terminal-fg/60">
            {busy ? 'Waiting for your passkey…' : 'Passkey prompt dismissed.'}
            {!busy && (
              <button type="button" onClick={runPasskey} className="ml-2 text-terminal-active hover:underline">
                Try again
              </button>
            )}
          </p>
        )}

        {(method === 'totp' || method === 'email_otp') && (
          <form onSubmit={submitCode} className="space-y-2">
            <label className="block text-xs font-mono text-terminal-fg/60" htmlFor="stepup-code">
              {method === 'totp' ? 'Authenticator code' : emailSent ? 'Code from your e-mail' : 'Sending e-mail code…'}
            </label>
            <input
              id="stepup-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-terminal-fg tracking-widest focus:outline-none focus:border-terminal-active"
            />
            <button
              type="submit"
              disabled={busy || !code.trim()}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-xs hover:bg-blue-600 disabled:opacity-50"
            >
              {busy ? 'Verifying…' : 'Verify'}
            </button>
            {method === 'email_otp' && emailSent && (
              <button type="button" onClick={sendEmail} disabled={busy} className="text-[0.625rem] font-mono text-terminal-fg/40 hover:text-terminal-fg">
                Resend code
              </button>
            )}
          </form>
        )}

        {error && <p className="text-xs font-mono text-red-400">{error}</p>}

        <div className="flex items-center justify-between pt-1">
          {method !== null && methods.length > 1 ? (
            <button type="button" onClick={() => { setMethod(null); setCode(''); setError('') }} className="text-xs font-mono text-terminal-fg/40 hover:text-terminal-fg">
              ← Other method
            </button>
          ) : <span />}
          <button type="button" onClick={onCancel} className="text-xs font-mono text-terminal-fg/40 hover:text-terminal-fg">
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

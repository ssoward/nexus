import { useEffect, useState } from 'react'
import client from '@/api/client'

interface TotpSetupResponse {
  provisioning_uri: string
  qr_code_base64: string
}

interface Props {
  hasTotp: boolean
  onClose: () => void
}

export function TotpSetupModal({ hasTotp, onClose }: Props) {
  const [step, setStep] = useState<'loading' | 'confirm' | 'qr' | 'done'>(
    hasTotp ? 'confirm' : 'loading'
  )
  const [currentCode, setCurrentCode] = useState('')
  const [qr, setQr] = useState<string | null>(null)
  const [uri, setUri] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const callSetup = async (code?: string) => {
    setLoading(true)
    setError('')
    try {
      const form = new FormData()
      if (code) form.append('totp_code', code)
      const res = await client.post<TotpSetupResponse>('/auth/setup-totp', form)
      setQr(res.data.qr_code_base64)
      setUri(res.data.provisioning_uri)
      setStep('qr')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail ?? 'Failed to generate QR code.')
      if (step === 'loading') setStep('confirm')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!hasTotp) callSetup()
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-[#161b22] border border-terminal-border rounded-lg p-6 w-full max-w-sm mx-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-mono font-bold text-terminal-fg">Set Up Authenticator</h2>
          <button
            onClick={onClose}
            className="text-terminal-fg/40 hover:text-terminal-fg font-mono text-lg leading-none"
          >
            ×
          </button>
        </div>

        {step === 'loading' && (
          <p className="text-sm font-mono text-terminal-fg/50 text-center py-4">Generating…</p>
        )}

        {step === 'confirm' && (
          <div className="space-y-3">
            <p className="text-xs text-terminal-fg/60 font-mono">
              Enter your current 6-digit TOTP code to authorize replacing your authenticator.
            </p>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder="000000"
              value={currentCode}
              onChange={e => setCurrentCode(e.target.value.replace(/\D/g, ''))}
              className="w-full px-3 py-2 rounded bg-[#0d1117] border border-terminal-border text-terminal-fg font-mono text-center tracking-widest text-lg focus:outline-none focus:border-terminal-active"
              autoFocus
            />
            {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
            <button
              onClick={() => callSetup(currentCode)}
              disabled={loading || currentCode.length !== 6}
              className="w-full py-2 rounded bg-terminal-active hover:bg-terminal-active/80 disabled:opacity-40 text-white font-mono text-sm"
            >
              {loading ? 'Verifying…' : 'Continue'}
            </button>
          </div>
        )}

        {step === 'qr' && qr && (
          <div className="space-y-3">
            <p className="text-xs text-terminal-fg/60 font-mono">
              Scan with Google Authenticator, Authy, or any TOTP app.
              You'll need the code on every sign-in.
            </p>
            <img
              src={`data:image/png;base64,${qr}`}
              alt="TOTP QR Code"
              className="w-full rounded border border-terminal-border"
            />
            <p className="text-xs text-terminal-fg/30 font-mono break-all">{uri}</p>
            <button
              onClick={() => setStep('done')}
              className="w-full py-2 rounded bg-green-700 hover:bg-green-600 text-white font-mono text-sm"
            >
              Done — I've scanned it
            </button>
          </div>
        )}

        {step === 'done' && (
          <div className="space-y-3">
            <p className="text-sm text-green-400 font-mono">
              Authenticator configured. Your next sign-in will require the 6-digit code.
            </p>
            <button
              onClick={onClose}
              className="w-full py-2 rounded bg-terminal-active text-white font-mono text-sm"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

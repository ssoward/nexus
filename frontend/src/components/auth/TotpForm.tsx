// Standalone TOTP setup form — used during initial onboarding
import { useState } from 'react'
import client from '@/api/client'

interface TotpSetupResponse {
  provisioning_uri: string
  qr_code_base64: string
}

export function TotpSetupForm() {
  const [qr, setQr] = useState<string | null>(null)
  const [uri, setUri] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const handleSetup = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const data = new FormData(form)
    setLoading(true)
    setError('')
    try {
      const res = await client.post<TotpSetupResponse>('/auth/setup-totp', data)
      setQr(res.data.qr_code_base64)
      setUri(res.data.provisioning_uri)
    } catch {
      setError('Failed to set up TOTP. Are you already authenticated?')
    } finally {
      setLoading(false)
    }
  }

  if (done) {
    return (
      <div className="text-green-400 font-mono text-sm">
        TOTP configured. You can now log in with your authenticator app.
      </div>
    )
  }

  return (
    <div className="max-w-sm space-y-4">
      {!qr ? (
        <form onSubmit={handleSetup} className="space-y-3">
          <p className="text-sm text-terminal-fg/60 font-mono">
            Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.)
          </p>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 rounded bg-terminal-active text-white font-mono text-sm"
          >
            {loading ? 'Generating…' : 'Generate TOTP QR Code'}
          </button>
          {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
        </form>
      ) : (
        <div className="space-y-3">
          <img src={`data:image/png;base64,${qr}`} alt="TOTP QR Code" className="border border-white rounded" />
          <p className="text-xs text-terminal-fg/40 font-mono break-all">{uri}</p>
          <button
            onClick={() => setDone(true)}
            className="px-4 py-2 rounded bg-green-700 text-white font-mono text-sm"
          >
            Done — I've scanned it
          </button>
        </div>
      )}
    </div>
  )
}

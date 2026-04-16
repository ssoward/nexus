import { useEffect, useState } from 'react'
import client from '@/api/client'

interface TotpSetupResponse {
  provisioning_uri: string
  qr_code_base64: string
}

interface Props {
  onClose: () => void
}

export function TotpSetupModal({ onClose }: Props) {
  const [qr, setQr] = useState<string | null>(null)
  const [uri, setUri] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    client.post<TotpSetupResponse>('/auth/setup-totp')
      .then(res => {
        setQr(res.data.qr_code_base64)
        setUri(res.data.provisioning_uri)
      })
      .catch(() => setError('Failed to generate QR code. Try signing out and back in.'))
      .finally(() => setLoading(false))
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

        {loading && (
          <p className="text-sm font-mono text-terminal-fg/50 text-center py-4">Generating…</p>
        )}

        {error && (
          <p className="text-xs text-red-400 font-mono">{error}</p>
        )}

        {!loading && !error && !done && qr && (
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
              onClick={() => setDone(true)}
              className="w-full py-2 rounded bg-green-700 hover:bg-green-600 text-white font-mono text-sm"
            >
              Done — I've scanned it
            </button>
          </div>
        )}

        {done && (
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

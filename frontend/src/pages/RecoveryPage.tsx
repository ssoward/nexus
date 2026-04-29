import { useEffect, useState } from 'react'
import { resetRecovery } from '@/api/auth'

export function RecoveryPage() {
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [detail, setDetail] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')

    if (!token) {
      setDetail('Invalid recovery link.')
      setStatus('error')
      return
    }

    resetRecovery(token)
      .then(() => setStatus('success'))
      .catch(err => {
        const msg = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        setDetail(msg ?? 'Invalid or expired recovery link.')
        setStatus('error')
      })
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-terminal-bg">
      <div className="w-full max-w-sm bg-[#161b22] border border-terminal-border rounded-lg p-8 space-y-4">
        <h1 className="text-xl font-mono font-bold text-terminal-fg">Account Recovery</h1>

        {status === 'loading' && (
          <p className="text-sm font-mono text-terminal-fg/50 animate-pulse">Verifying link…</p>
        )}

        {status === 'success' && (
          <>
            <p className="text-sm font-mono text-green-400">MFA reset successfully.</p>
            <p className="text-xs font-mono text-terminal-fg/60">
              Your verification method has been cleared. On your next login you'll be prompted
              to set up a new one.
            </p>
            <a
              href="/login"
              className="block w-full py-2 rounded bg-terminal-active text-white font-mono text-sm text-center hover:bg-blue-600"
            >
              Go to sign in
            </a>
          </>
        )}

        {status === 'error' && (
          <>
            <p className="text-sm font-mono text-red-400">{detail}</p>
            <a
              href="/login"
              className="block w-full py-2 rounded bg-terminal-border text-terminal-fg font-mono text-sm text-center hover:bg-terminal-active hover:text-white"
            >
              Back to sign in
            </a>
          </>
        )}
      </div>
    </div>
  )
}

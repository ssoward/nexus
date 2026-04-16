import { useState } from 'react'
import { PRESET_COMMANDS } from '@/types/session'
import type { CreateSessionRequest } from '@/types/session'

const PRESET_MAP = Object.fromEntries(PRESET_COMMANDS.map((p) => [p.value, p]))

interface Props {
  onConfirm: (req: CreateSessionRequest) => Promise<void>
  onClose: () => void
  maxReached: boolean
}

export function NewSessionDialog({ onConfirm, onClose, maxReached }: Props) {
  const [name, setName] = useState('')
  const [image, setImage] = useState<string>(PRESET_COMMANDS[0].value)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Session name is required')
      return
    }
    setLoading(true)
    setError('')
    try {
      // Estimate terminal dimensions from viewport so the PTY spawns at
      // roughly the right size — avoids jumbled TUI output from Claude Code
      // before the resize-on-connect fires.
      const charW = 8.4   // approx px per char at 14px JetBrains Mono
      const charH = 17    // approx px per line
      const availW = Math.max(400, window.innerWidth - 300) // minus sidebar
      const availH = Math.max(200, window.innerHeight - 100) // minus header
      const cols = Math.max(80, Math.min(300, Math.floor(availW / charW)))
      const rows = Math.max(24, Math.min(80, Math.floor(availH / charH)))
      await onConfirm({ name: name.trim(), image, cols, rows })
      onClose()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create session'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#161b22] border border-terminal-border rounded-lg p-6 w-full max-w-md">
        <h2 className="text-terminal-fg font-mono text-lg mb-4">New Terminal Session</h2>

        {maxReached && (
          <div className="mb-4 text-sm text-red-400 font-mono">
            Maximum sessions reached (6). Delete a session first.
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-terminal-fg/60 font-mono mb-1">Session Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-session"
              maxLength={64}
              className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active"
              disabled={maxReached}
            />
          </div>

          <div>
            <label className="block text-xs text-terminal-fg/60 font-mono mb-1">Session Type</label>
            <select
              value={image}
              onChange={(e) => setImage(e.target.value)}
              className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-terminal-fg focus:outline-none focus:border-terminal-active"
              disabled={maxReached}
            >
              {PRESET_COMMANDS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
            {PRESET_MAP[image] && (
              <p className="mt-1 text-[10px] font-mono text-terminal-fg/40">{PRESET_MAP[image].description}</p>
            )}
          </div>

          {error && <p className="text-xs text-red-400 font-mono">{error}</p>}

          <div className="flex gap-2 justify-end pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-mono rounded border border-terminal-border text-terminal-fg/70 hover:bg-terminal-border"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || maxReached}
              className="px-4 py-2 text-sm font-mono rounded bg-terminal-active text-white hover:bg-blue-600 disabled:opacity-50"
            >
              {loading ? 'Creating…' : 'Create Session'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

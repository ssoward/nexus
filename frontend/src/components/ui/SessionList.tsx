import { useState } from 'react'
import type { Session } from '@/types/session'
import { StatusBadge } from './StatusBadge'
import { PaneControls } from '@/components/terminal/PaneControls'
import { NewSessionDialog } from './NewSessionDialog'
import { useSession } from '@/hooks/useSession'
import { useSessionStore } from '@/store/sessionStore'
import { useInactivityDetector } from '@/hooks/useInactivityDetector'
import { toast } from '@/store/toastStore'

const MAX_SESSIONS = 6

interface Props {
  onClose?: () => void
}

export function SessionList({ onClose }: Props) {
  const { sessions, create, remove } = useSession()
  const { activePaneIndex } = useSessionStore()
  const [showDialog, setShowDialog] = useState(false)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  const runningCount = sessions.filter((s) => s.status === 'running').length
  const maxReached = runningCount >= MAX_SESSIONS

  const handleCreate = async (req: Parameters<typeof create>[0]) => {
    await create(req)
    onClose?.()
  }

  const handleDeleteRequest = (id: string) => {
    setPendingDeleteId(id)
  }

  const handleDeleteConfirm = async (session: Session) => {
    setPendingDeleteId(null)
    try {
      await remove(session.id)
      toast.success(`Session "${session.name}" deleted`)
    } catch {
      toast.error(`Failed to delete session "${session.name}"`)
    }
  }

  return (
    <aside className="w-full h-full flex flex-col bg-[#0d1117] border-r border-terminal-border">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-terminal-border shrink-0">
        <span className="text-xs font-mono text-terminal-fg/60 uppercase tracking-wider">Sessions</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDialog(true)}
            className="text-xs px-2 py-1 rounded bg-terminal-active/20 hover:bg-terminal-active/40 text-terminal-active font-mono"
            title="New session"
          >
            + New
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="text-terminal-fg/40 hover:text-terminal-fg p-1 rounded"
              aria-label="Close panel"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 && (
          <p className="px-3 py-4 text-xs font-mono text-terminal-fg/30 text-center">
            No sessions yet
          </p>
        )}
        {sessions.map((session, idx) => (
          <div
            key={session.id}
            className={`px-3 py-2 border-b border-terminal-border/50 ${
              idx === activePaneIndex ? 'bg-terminal-active/10' : 'hover:bg-white/5'
            }`}
          >
            {pendingDeleteId === session.id ? (
              <div className="flex flex-col gap-1.5 py-0.5">
                <p className="text-xs font-mono text-terminal-fg/70">
                  Delete <span className="text-terminal-fg font-semibold">{session.name}</span>?
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleDeleteConfirm(session)}
                    className="flex-1 py-1 text-xs font-mono rounded bg-red-700 hover:bg-red-600 text-white"
                  >
                    Delete
                  </button>
                  <button
                    onClick={() => setPendingDeleteId(null)}
                    className="flex-1 py-1 text-xs font-mono rounded border border-terminal-border text-terminal-fg/60 hover:bg-terminal-border"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-1">
                  <div className="min-w-0">
                    <p className="text-sm font-mono text-terminal-fg truncate">{session.name}</p>
                    <p className="text-xs text-terminal-fg/40 font-mono truncate">{session.image}</p>
                  </div>
                  <PaneControls
                    session={session}
                    onDelete={handleDeleteRequest}
                    onFocus={onClose}
                  />
                </div>
                <div className="mt-1 flex items-center gap-1.5">
                  <StatusBadge status={session.status} />
                  <SessionIdleBadge sessionId={session.id} status={session.status} />
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {showDialog && (
        <NewSessionDialog
          onConfirm={handleCreate}
          onClose={() => setShowDialog(false)}
          maxReached={maxReached}
        />
      )}
    </aside>
  )
}

function SessionIdleBadge({ sessionId, status }: { sessionId: string; status: string }) {
  const isIdle = useInactivityDetector(sessionId, status)
  if (!isIdle) return null
  return (
    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border bg-amber-900/40 text-amber-400 border-amber-700">
      idle
    </span>
  )
}

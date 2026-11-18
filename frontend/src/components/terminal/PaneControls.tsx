import { useSessionStore, attachedSessions } from '@/store/sessionStore'
import type { Session } from '@/types/session'

interface Props {
  session: Session
  onDelete: (id: string) => void
  onFocus?: () => void  // optional callback after focus (e.g. close mobile drawer)
}

export function PaneControls({ session, onDelete, onFocus }: Props) {
  const setActiveSession = useSessionStore((s) => s.setActiveSession)
  // Index within the attached list — the same order the panes and the
  // Ctrl+1–6 shortcuts use (stopped/errored sessions have no pane).
  const idx = useSessionStore((s) => attachedSessions(s.sessions).findIndex((x) => x.id === session.id))

  const handleFocus = () => {
    if (idx >= 0) setActiveSession(session.id)
    onFocus?.()
  }

  return (
    <div className="flex items-center gap-1">
      {idx >= 0 && (
        <button
          onClick={handleFocus}
          className="text-xs px-1.5 py-0.5 rounded bg-terminal-border hover:bg-terminal-active/20 text-terminal-fg"
          title={`Focus pane (Ctrl+${idx + 1})`}
        >
          Focus
        </button>
      )}
      <button
        onClick={() => onDelete(session.id)}
        className="text-xs px-1.5 py-0.5 rounded bg-red-900/30 hover:bg-red-900/60 text-red-400"
        title="Delete session"
      >
        ✕
      </button>
    </div>
  )
}

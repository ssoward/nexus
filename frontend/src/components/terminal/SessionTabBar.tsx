import { clsx } from 'clsx'
import { useSessionStore, activeIndexIn } from '@/store/sessionStore'
import { useInactivityDetector } from '@/hooks/useInactivityDetector'
import { LayoutControls, FullscreenButton } from './LayoutControls'
import type { Session } from '@/types/session'

interface Props {
  sessions: Session[]
  /** Full screen is on: the header is hidden, so this bar carries the layout controls. */
  immersive: boolean
  onToggleFullscreen: () => void
  isMobile: boolean
}

/**
 * Slim strip of shell tabs. Shown in focus layout (to switch which shell fills
 * the screen) and in full screen (where it replaces the hidden header).
 */
export function SessionTabBar({ sessions, immersive, onToggleFullscreen, isMobile }: Props) {
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const setActiveSession = useSessionStore((s) => s.setActiveSession)
  const activeIdx = activeIndexIn(sessions, activeSessionId)

  return (
    <div
      className="shrink-0 flex items-center gap-1 px-1 bg-[#161b22] border-b border-terminal-border min-w-0"
      role="tablist"
      aria-label="Shells"
    >
      <div className="flex items-stretch gap-0.5 flex-1 min-w-0 overflow-x-auto">
        {sessions.map((s, idx) => (
          <SessionTab
            key={s.id}
            session={s}
            index={idx}
            active={idx === activeIdx}
            onSelect={() => setActiveSession(s.id)}
          />
        ))}
      </div>
      {immersive && <LayoutControls showFocus={!isMobile} />}
      <FullscreenButton active={immersive} onClick={onToggleFullscreen} />
    </div>
  )
}

function SessionTab({ session, index, active, onSelect }: { session: Session; index: number; active: boolean; onSelect: () => void }) {
  const isIdle = useInactivityDetector(session.id, session.status)
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onSelect}
      title={index < 6 ? `${session.name} (Ctrl+${index + 1})` : session.name}
      className={clsx(
        'flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono whitespace-nowrap border-b-2 transition-colors max-w-[14rem]',
        active
          ? 'border-terminal-active text-terminal-fg bg-terminal-active/10'
          : 'border-transparent text-terminal-fg/50 hover:text-terminal-fg hover:bg-white/5',
      )}
    >
      <span
        className={clsx(
          'shrink-0 rounded-full w-1.5 h-1.5',
          isIdle ? 'bg-amber-500 animate-pulse' :
          session.status === 'running' ? 'bg-green-500' :
          session.status === 'recovery_pending' ? 'bg-yellow-500' : 'bg-gray-500',
        )}
      />
      <span className="truncate">{session.name}</span>
      {index < 6 && <span className="text-terminal-fg/30 text-[0.625rem]">{index + 1}</span>}
    </button>
  )
}

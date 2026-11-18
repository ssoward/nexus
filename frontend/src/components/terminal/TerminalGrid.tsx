import { useRef } from 'react'
import { useSessionStore, activeIndexIn } from '@/store/sessionStore'
import { TerminalPane } from './TerminalPane'
import type { Session } from '@/types/session'

interface Props {
  sessions: Session[]
  isMobile: boolean
  /** Desktop only: show just the active shell, filling the whole terminal area. */
  focus?: boolean
}

function getGridClass(count: number): string {
  if (count <= 1) return 'grid-cols-1 grid-rows-1'
  if (count === 2) return 'grid-cols-2 grid-rows-1'
  if (count <= 4) return 'grid-cols-2 grid-rows-2'
  return 'grid-cols-3 grid-rows-2'
}

export function TerminalGrid({ sessions, isMobile, focus = false }: Props) {
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const setActiveSession = useSessionStore((s) => s.setActiveSession)
  const activeIdx = activeIndexIn(sessions, activeSessionId)
  const select = (idx: number) => {
    const s = sessions[Math.max(0, Math.min(sessions.length - 1, idx))]
    if (s) setActiveSession(s.id)
  }

  // Touch tracking refs for swipe-to-switch gesture (mobile only)
  const touchStartX = useRef(0)
  const touchStartY = useRef(0)

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
  }

  const handleTouchEnd = (e: React.TouchEvent) => {
    const dx = e.changedTouches[0].clientX - touchStartX.current
    const dy = e.changedTouches[0].clientY - touchStartY.current
    // Only fire for clearly horizontal swipes (avoids interfering with terminal scroll)
    if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 2) {
      select(dx < 0 ? activeIdx + 1 : activeIdx - 1)
    }
  }

  if (sessions.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-terminal-fg/40 font-mono text-sm p-4 text-center">
        No active sessions. Open the panel to create one.
      </div>
    )
  }

  // ── Mobile: single pane + prev/next nav ──────────────────────────────────
  if (isMobile) {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        {/* All panes rendered (keeps WS alive), only active visible.
            Touch handlers here catch swipes that bubble up from the terminal. */}
        <div
          className="flex-1 min-h-0 relative"
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          {sessions.map((session, idx) => (
            <div
              key={session.id}
              className={`absolute inset-0 ${idx === activeIdx ? 'block' : 'hidden'}`}
            >
              <TerminalPane
                session={session}
                isActive={idx === activeIdx}
                onClick={() => setActiveSession(session.id)}
              />
            </div>
          ))}
        </div>

        {/* Bottom nav — only shown when >1 session */}
        {sessions.length > 1 && (
          <div className="shrink-0 flex items-center bg-[#161b22] border-t border-terminal-border px-2 py-1 gap-2">
            <button
              onClick={() => select(activeIdx - 1)}
              disabled={activeIdx === 0}
              className="px-3 py-1.5 text-xs font-mono rounded border border-terminal-border text-terminal-fg/60 hover:bg-terminal-border disabled:opacity-30"
            >
              ‹ Prev
            </button>

            {/* Dot indicators */}
            <div className="flex-1 flex items-center justify-center gap-1.5">
              {sessions.map((s, idx) => (
                <button
                  key={s.id}
                  onClick={() => setActiveSession(s.id)}
                  className={`rounded-full transition-all ${
                    idx === activeIdx
                      ? 'w-4 h-2 bg-terminal-active'
                      : 'w-2 h-2 bg-terminal-border hover:bg-terminal-fg/40'
                  }`}
                  title={s.name}
                />
              ))}
            </div>

            <button
              onClick={() => select(activeIdx + 1)}
              disabled={activeIdx === sessions.length - 1}
              className="px-3 py-1.5 text-xs font-mono rounded border border-terminal-border text-terminal-fg/60 hover:bg-terminal-border disabled:opacity-30"
            >
              Next ›
            </button>
          </div>
        )}
      </div>
    )
  }

  // ── Desktop: multi-pane grid, or focus (one shell fills the area) ────────
  // Both modes render the same keyed wrapper per session under the same parent,
  // so toggling between them only changes classes: no TerminalPane remounts,
  // no WebSocket reconnect, scrollback preserved. In focus mode the other shells
  // stay mounted at full size but `invisible` (not display:none), so their PTY
  // geometry already matches when you switch to them and they can't take focus.
  return (
    <div
      className={
        focus
          ? 'flex-1 relative min-h-0'
          : `flex-1 grid gap-1 p-1 min-h-0 ${getGridClass(sessions.length)}`
      }
    >
      {sessions.map((session, idx) => (
        <div
          key={session.id}
          className={
            focus
              ? `absolute inset-1 ${idx === activeIdx ? '' : 'invisible pointer-events-none'}`
              : 'min-h-0 min-w-0'
          }
          aria-hidden={focus && idx !== activeIdx ? true : undefined}
        >
          <TerminalPane
            session={session}
            isActive={idx === activeIdx}
            onClick={() => setActiveSession(session.id)}
          />
        </div>
      ))}
    </div>
  )
}

import { useEffect, useRef } from 'react'
import { useSessionStore } from '@/store/sessionStore'
import { TerminalPane } from './TerminalPane'
import type { Session } from '@/types/session'

interface Props {
  sessions: Session[]
  isMobile: boolean
}

function getGridClass(count: number): string {
  if (count <= 1) return 'grid-cols-1 grid-rows-1'
  if (count === 2) return 'grid-cols-2 grid-rows-1'
  if (count <= 4) return 'grid-cols-2 grid-rows-2'
  return 'grid-cols-3 grid-rows-2'
}

export function TerminalGrid({ sessions, isMobile }: Props) {
  const { activePaneIndex, setActivePane } = useSessionStore()

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
    const activeIdx = Math.min(activePaneIndex, sessions.length - 1)
    // Only fire for clearly horizontal swipes (avoids interfering with terminal scroll)
    if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 2) {
      if (dx < 0) setActivePane(Math.min(sessions.length - 1, activeIdx + 1))
      else        setActivePane(Math.max(0, activeIdx - 1))
    }
  }

  // Clamp active index when sessions are removed
  useEffect(() => {
    if (activePaneIndex >= sessions.length && sessions.length > 0) {
      setActivePane(sessions.length - 1)
    }
  }, [sessions.length, activePaneIndex, setActivePane])

  // Keyboard shortcut: Ctrl+1–6 to switch panes
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '6') {
        const idx = parseInt(e.key, 10) - 1
        if (idx < sessions.length) {
          e.preventDefault()
          setActivePane(idx)
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [sessions.length, setActivePane])

  if (sessions.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-terminal-fg/40 font-mono text-sm p-4 text-center">
        No active sessions. Open the panel to create one.
      </div>
    )
  }

  // ── Mobile: single pane + prev/next nav ──────────────────────────────────
  if (isMobile) {
    const activeIdx = Math.min(activePaneIndex, sessions.length - 1)
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
                onClick={() => setActivePane(idx)}
              />
            </div>
          ))}
        </div>

        {/* Bottom nav — only shown when >1 session */}
        {sessions.length > 1 && (
          <div className="shrink-0 flex items-center bg-[#161b22] border-t border-terminal-border px-2 py-1 gap-2">
            <button
              onClick={() => setActivePane(Math.max(0, activeIdx - 1))}
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
                  onClick={() => setActivePane(idx)}
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
              onClick={() => setActivePane(Math.min(sessions.length - 1, activeIdx + 1))}
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

  // ── Desktop: multi-pane grid ─────────────────────────────────────────────
  return (
    <div className={`flex-1 grid gap-1 p-1 min-h-0 ${getGridClass(sessions.length)}`}>
      {sessions.map((session, idx) => (
        <TerminalPane
          key={session.id}
          session={session}
          isActive={idx === activePaneIndex}
          onClick={() => setActivePane(idx)}
        />
      ))}
    </div>
  )
}

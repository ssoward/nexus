import { useEffect } from 'react'
import { useSessionStore } from '@/store/sessionStore'
import { TerminalPane } from './TerminalPane'
import type { Session } from '@/types/session'

interface Props {
  sessions: Session[]
  isMobile: boolean
}

export function PriorityLayout({ sessions, isMobile }: Props) {
  const { primarySessionId, setPrimarySession, activePaneIndex, setActivePane } = useSessionStore()

  // Auto-select first session as primary if none set
  useEffect(() => {
    if (!primarySessionId && sessions.length > 0) {
      setPrimarySession(sessions[0].id)
    }
    // Clear primary if removed
    if (primarySessionId && !sessions.find((s) => s.id === primarySessionId)) {
      setPrimarySession(sessions[0]?.id ?? null)
    }
  }, [sessions, primarySessionId, setPrimarySession])

  if (sessions.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-terminal-fg/40 font-mono text-sm p-4 text-center">
        No active sessions. Open the panel to create one.
      </div>
    )
  }

  const primary = sessions.find((s) => s.id === primarySessionId) ?? sessions[0]
  const thumbnails = sessions.filter((s) => s.id !== primary.id)
  const primaryIdx = sessions.findIndex((s) => s.id === primary.id)

  const handleThumbnailClick = (id: string) => {
    setPrimarySession(id)
    const idx = sessions.findIndex((s) => s.id === id)
    if (idx >= 0) setActivePane(idx)
  }

  if (sessions.length === 1) {
    return (
      <div className="flex-1 flex flex-col min-h-0 p-1">
        <TerminalPane
          session={primary}
          isActive={true}
          onClick={() => setActivePane(0)}
        />
      </div>
    )
  }

  // Mobile: primary on top, thumbnail strip at bottom
  if (isMobile) {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex-[4] min-h-0 p-1">
          <TerminalPane
            session={primary}
            isActive={primaryIdx === activePaneIndex}
            onClick={() => setActivePane(primaryIdx)}
          />
        </div>
        <div className="flex-[1] flex flex-row gap-1 p-1 overflow-x-auto min-h-[80px]">
          {thumbnails.map((s) => {
            const idx = sessions.findIndex((x) => x.id === s.id)
            return (
              <div
                key={s.id}
                className="min-w-[120px] flex-shrink-0 cursor-pointer opacity-70 hover:opacity-100 transition-opacity"
                onClick={() => handleThumbnailClick(s.id)}
              >
                <TerminalPane
                  session={s}
                  isActive={idx === activePaneIndex}
                  onClick={() => handleThumbnailClick(s.id)}
                />
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // Desktop: primary on left (~80%), thumbnails stacked on right (~20%)
  return (
    <div className="flex-1 flex flex-row gap-1 p-1 min-h-0">
      <div className="flex-[4] min-w-0">
        <TerminalPane
          session={primary}
          isActive={primaryIdx === activePaneIndex}
          onClick={() => setActivePane(primaryIdx)}
        />
      </div>
      <div className="flex-[1] flex flex-col gap-1 overflow-y-auto min-w-[160px]">
        {thumbnails.map((s) => {
          const idx = sessions.findIndex((x) => x.id === s.id)
          return (
            <div
              key={s.id}
              className="flex-1 min-h-[60px] cursor-pointer opacity-70 hover:opacity-100 transition-opacity"
              onClick={() => handleThumbnailClick(s.id)}
            >
              <TerminalPane
                session={s}
                isActive={idx === activePaneIndex}
                onClick={() => handleThumbnailClick(s.id)}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

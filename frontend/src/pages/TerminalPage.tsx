import { useCallback, useEffect, useRef, useState } from 'react'
import { TerminalGrid } from '@/components/terminal/TerminalGrid'
import { PriorityLayout } from '@/components/terminal/PriorityLayout'
import { SessionList } from '@/components/ui/SessionList'
import { OrchestratorPanel } from '@/components/ui/OrchestratorPanel'
import { PageList } from '@/components/ui/PageList'
import { SettingsPanel } from '@/components/ui/SettingsPanel'
import { EmbeddedPage } from '@/components/ui/EmbeddedPage'
import { TotpSetupModal } from '@/components/auth/TotpSetupModal'
import { HelpModal } from '@/components/ui/HelpModal'
import type { EmbeddedPage as EmbeddedPageType } from '@/types/page'
import { useSession } from '@/hooks/useSession'
import { useAuth } from '@/hooks/useAuth'
import { useIsMobile } from '@/hooks/useIsMobile'
import { useSessionStore } from '@/store/sessionStore'
import { useAutoPromote } from '@/hooks/useAutoPromote'

export function TerminalPage() {
  const { logout, user } = useAuth()
  const { sessions, refresh } = useSession()
  const isMobile = useIsMobile()
  const { layoutMode, setLayoutMode, autoPromote, setAutoPromote } = useSessionStore()
  const [sidebarOpen, setSidebarOpen] = useState(!isMobile)
  const [sidebarWidth, setSidebarWidth] = useState(256)
  const sidebarRef = useRef<HTMLDivElement>(null)
  const [terminalPct, setTerminalPct] = useState(60)
  const splitContainerRef = useRef<HTMLDivElement>(null)
  const [sidebarTab, setSidebarTab] = useState<'sessions' | 'orchestrator' | 'pages' | 'settings'>('sessions')
  const [showTotpSetup, setShowTotpSetup] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [activePage, setActivePage] = useState<EmbeddedPageType | null>(null)

  // Close sidebar by default when switching to mobile; open on desktop
  useEffect(() => {
    setSidebarOpen(!isMobile)
  }, [isMobile])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 10_000)
    return () => clearInterval(interval)
  }, [refresh])

  // Refresh session list when returning from a backgrounded tab (>5s away)
  const pageHiddenAt = useRef(0)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) {
        pageHiddenAt.current = Date.now()
      } else if (pageHiddenAt.current && Date.now() - pageHiddenAt.current > 5_000) {
        refresh()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [refresh])

  const handleSidebarResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    document.body.style.userSelect = 'none'
    const onMove = (me: MouseEvent) => {
      const w = Math.max(160, Math.min(520, me.clientX))
      // Direct DOM update so sidebar and main area move in the same frame
      if (sidebarRef.current) sidebarRef.current.style.width = `${w}px`
    }
    const onUp = (me: MouseEvent) => {
      document.body.style.userSelect = ''
      // Sync React state so the value survives re-renders (e.g. sidebar toggle)
      setSidebarWidth(Math.max(160, Math.min(520, me.clientX)))
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [])

  const handlePageResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    const container = splitContainerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    document.body.style.userSelect = 'none'
    const onMove = (me: MouseEvent) => {
      const pct = ((me.clientX - rect.left) / rect.width) * 100
      setTerminalPct(Math.max(20, Math.min(80, pct)))
    }
    const onUp = () => {
      document.body.style.userSelect = ''
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [])

  const running = sessions.filter((s) => s.status === 'running')
  useAutoPromote(running)

  return (
    <div className="flex h-dvh bg-terminal-bg overflow-hidden">

      {/* ── Mobile backdrop ── */}
      {isMobile && sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ── */}
      <div
        ref={sidebarRef}
        className={[
          'shrink-0 flex flex-col overflow-hidden',
          isMobile
            ? `fixed inset-0 z-40 bg-[#161b22] transition-all duration-200 ${sidebarOpen ? 'w-full' : 'w-0'}`
            : `bg-[#161b22] ${sidebarOpen ? '' : 'w-0'}`,
        ].join(' ')}
        style={!isMobile && sidebarOpen ? { width: sidebarWidth } : undefined}
      >
        {/* Sidebar tab bar */}
        <div className="flex border-b border-terminal-border shrink-0">
          <button
            onClick={() => setSidebarTab('sessions')}
            className={`flex-1 py-1.5 ${isMobile ? 'text-xs' : 'text-[10px]'} font-mono uppercase tracking-wider transition-colors ${sidebarTab === 'sessions' ? 'text-terminal-active border-b border-terminal-active' : 'text-terminal-fg/40 hover:text-terminal-fg'}`}
          >
            Sessions
          </button>
          <button
            onClick={() => setSidebarTab('orchestrator')}
            className={`flex-1 py-1.5 ${isMobile ? 'text-xs' : 'text-[10px]'} font-mono uppercase tracking-wider transition-colors ${sidebarTab === 'orchestrator' ? 'text-terminal-active border-b border-terminal-active' : 'text-terminal-fg/40 hover:text-terminal-fg'}`}
          >
            Orch
          </button>
          <button
            onClick={() => setSidebarTab('pages')}
            className={`flex-1 py-1.5 ${isMobile ? 'text-xs' : 'text-[10px]'} font-mono uppercase tracking-wider transition-colors ${sidebarTab === 'pages' ? 'text-terminal-active border-b border-terminal-active' : 'text-terminal-fg/40 hover:text-terminal-fg'}`}
          >
            Pages
          </button>
          <button
            onClick={() => setSidebarTab('settings')}
            className={`flex-1 py-1.5 ${isMobile ? 'text-xs' : 'text-[10px]'} font-mono uppercase tracking-wider transition-colors ${sidebarTab === 'settings' ? 'text-terminal-active border-b border-terminal-active' : 'text-terminal-fg/40 hover:text-terminal-fg'}`}
          >
            Settings
          </button>
        </div>
        {sidebarTab === 'sessions' && <SessionList onClose={isMobile ? () => setSidebarOpen(false) : undefined} />}
        {sidebarTab === 'orchestrator' && <OrchestratorPanel onClose={isMobile ? () => setSidebarOpen(false) : undefined} />}
        {sidebarTab === 'pages' && <PageList onClose={isMobile ? () => setSidebarOpen(false) : undefined} onSelectPage={(p) => { setActivePage(p); if (isMobile && p) setSidebarOpen(false) }} activePage={activePage} />}
        {sidebarTab === 'settings' && <SettingsPanel onClose={isMobile ? () => setSidebarOpen(false) : undefined} />}
      </div>

      {/* ── Sidebar resize handle ── */}
      {!isMobile && sidebarOpen && (
        <div
          onMouseDown={handleSidebarResizeStart}
          className="relative w-1.5 shrink-0 cursor-col-resize group z-10 self-stretch"
        >
          <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-terminal-border group-hover:bg-terminal-active/60 transition-colors" />
        </div>
      )}

      {/* ── Main area ── */}
      <div className="flex flex-col flex-1 min-w-0">
        <header className="flex items-center gap-2 px-3 py-2 bg-[#161b22] border-b border-terminal-border shrink-0 overflow-x-hidden min-w-0">
          {/* Sidebar toggle */}
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="p-1.5 rounded text-terminal-fg/50 hover:text-terminal-fg hover:bg-terminal-border transition-colors"
            title={sidebarOpen ? 'Hide sessions' : 'Show sessions'}
            aria-label="Toggle session panel"
          >
            {/* Hamburger / close icon */}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              {sidebarOpen && !isMobile
                ? <path d="M6 2h8v1.5H6zm0 5h8v1.5H6zm0 5h8V14H6zM1 2h3.5v12H1z" />
                : <path d="M1 2h14v1.5H1zm0 5h14v1.5H1zm0 5h14V14H1z" />
              }
            </svg>
          </button>

          {/* Layout toggle */}
          <div className="flex items-center gap-0.5 mr-2">
            <button
              onClick={() => setLayoutMode('grid')}
              className={`p-1.5 rounded transition-colors ${layoutMode === 'grid' ? 'text-terminal-active bg-terminal-active/10' : 'text-terminal-fg/40 hover:text-terminal-fg'}`}
              title="Grid layout"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M1 1h6v6H1zm8 0h6v6H9zM1 9h6v6H1zm8 0h6v6H9z" />
              </svg>
            </button>
            <button
              onClick={() => setLayoutMode('priority')}
              className={`p-1.5 rounded transition-colors ${layoutMode === 'priority' ? 'text-terminal-active bg-terminal-active/10' : 'text-terminal-fg/40 hover:text-terminal-fg'}`}
              title="Priority layout"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M1 1h10v10H1zm12 0h2v4h-2zM13 6h2v5h-2z" />
              </svg>
            </button>
            {layoutMode === 'priority' && (
              <button
                onClick={() => setAutoPromote(!autoPromote)}
                className={`ml-1 p-1.5 rounded text-xs font-mono transition-colors ${autoPromote ? 'text-green-400 bg-green-900/20' : 'text-terminal-fg/40 bg-terminal-border/30'}`}
                title={autoPromote ? 'Auto-promote ON' : 'Auto-promote OFF'}
              >
                {autoPromote ? '▶' : '⏸'}
              </button>
            )}
          </div>

          <span className="font-mono text-sm text-terminal-fg/60 flex-1 truncate">
            Nexus — <span className="text-terminal-fg/40">{running.length} running</span>
          </span>

          <button
            onClick={() => window.location.reload()}
            className="p-1.5 rounded text-terminal-fg/40 hover:text-terminal-fg hover:bg-terminal-border transition-colors shrink-0"
            title="Reload app"
            aria-label="Reload app"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/>
              <path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/>
            </svg>
          </button>

          <button
            onClick={() => setShowHelp(true)}
            className="p-1.5 rounded text-terminal-fg/40 hover:text-terminal-fg hover:bg-terminal-border transition-colors shrink-0"
            title="Help"
            aria-label="Help"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 11.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm.75-3.75a.75.75 0 0 1-1.5 0v-.5c0-1.24 1.25-1.75 1.25-2.75a1.5 1.5 0 1 0-3 0 .75.75 0 0 1-1.5 0 3 3 0 1 1 5.75 1.2c-.2.55-.75.9-.75 1.55v.5z"/>
            </svg>
          </button>

          <button
            onClick={() => setShowTotpSetup(true)}
            className="p-1.5 rounded text-terminal-fg/40 hover:text-terminal-fg hover:bg-terminal-border transition-colors shrink-0"
            title="Set up authenticator app"
            aria-label="Set up 2FA"
          >
            {/* Lock icon */}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M11 6V5a3 3 0 1 0-6 0v1H3.5A1.5 1.5 0 0 0 2 7.5v6A1.5 1.5 0 0 0 3.5 15h9a1.5 1.5 0 0 0 1.5-1.5v-6A1.5 1.5 0 0 0 12.5 6H11zm-4.5 0V5a1.5 1.5 0 1 1 3 0v1h-3zm2.5 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
            </svg>
          </button>

          <button
            onClick={logout}
            className="text-xs font-mono text-terminal-fg/40 hover:text-terminal-fg px-2 py-1 rounded shrink-0"
          >
            Sign out
          </button>
        </header>

        {showTotpSetup && <TotpSetupModal hasTotp={user?.has_totp ?? false} onClose={() => setShowTotpSetup(false)} />}
        {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}

        {/* Mobile full-screen page overlay */}
        {activePage && isMobile && (
          <div className="fixed inset-0 z-50 flex flex-col bg-white">
            <div className="shrink-0 flex items-center gap-2 px-3 py-2 bg-[#161b22] border-b border-terminal-border">
              <button
                onClick={() => setActivePage(null)}
                className="p-1.5 rounded text-terminal-fg/60 hover:text-terminal-fg hover:bg-terminal-border transition-colors"
                aria-label="Back to terminals"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z"/>
                </svg>
              </button>
              <span className="text-xs font-mono text-terminal-fg truncate flex-1">{activePage.name}</span>
              <a
                href={activePage.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[10px] font-mono text-terminal-active hover:underline shrink-0"
              >
                Open in browser
              </a>
            </div>
            <iframe
              src={activePage.url}
              sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
              className="flex-1 w-full border-0"
              title={activePage.name}
            />
          </div>
        )}

        <div className="flex flex-1 min-h-0" ref={splitContainerRef}>
          <div
            className="flex flex-col min-h-0 min-w-0"
            style={activePage && !isMobile ? { flex: `${terminalPct} 1 0%` } : { flex: '1 1 0%' }}
          >
            {layoutMode === 'priority'
              ? <PriorityLayout sessions={running} isMobile={isMobile} />
              : <TerminalGrid sessions={running} isMobile={isMobile} />
            }
          </div>
          {activePage && !isMobile && (
            <>
              {/* Page resize handle */}
              <div
                onMouseDown={handlePageResizeStart}
                className="relative w-1.5 shrink-0 cursor-col-resize group self-stretch"
              >
                <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-terminal-border group-hover:bg-terminal-active/60 transition-colors" />
              </div>
              <div
                className="flex flex-col min-w-0 min-h-0"
                style={{ flex: `${100 - terminalPct} 1 0%` }}
              >
                <EmbeddedPage url={activePage.url} name={activePage.name} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

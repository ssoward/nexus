import { useEffect, useRef, useState, useCallback } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import '@xterm/xterm/css/xterm.css'
import { useTerminalSocket } from '@/hooks/useTerminalSocket'
import { useVisibilityReconnect } from '@/hooks/useVisibilityReconnect'
import { useInactivityDetector } from '@/hooks/useInactivityDetector'
import { useKeyboardGuard } from '@/hooks/useKeyboardGuard'
import { MobileKeyboardShim } from './MobileKeyboardShim'
import { MobileKeybar } from './MobileKeybar'
import type { Session } from '@/types/session'
import { clsx } from 'clsx'

interface Props {
  session: Session
  isActive: boolean
  onClick: () => void
}

export function TerminalPane({ session, isActive, onClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  // Use state (not ref) so hook consumers re-render when terminal is ready
  const [terminal, setTerminal] = useState<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const [isDead, setIsDead] = useState(false)
  const [deadReason, setDeadReason] = useState('')

  const isIdle = useInactivityDetector(session.id, session.status)
  const { isMobile, hiddenInputRef, showSoftKeyboard } = useKeyboardGuard()

  // Initialize xterm.js
  useEffect(() => {
    if (!containerRef.current) return

    const term = new Terminal({
      cursorBlink: true,
      // Slightly larger font on touch devices for readability
      fontSize: isMobile ? 13 : 14,
      fontFamily: '"JetBrains Mono", "Fira Code", monospace',
      theme: {
        background: '#0d1117',
        foreground: '#c9d1d9',
        cursor: '#388bfd',
        selectionBackground: '#388bfd44',
      },
      scrollback: 5000,
      allowProposedApi: true,
      // When Claude Code enables bracketedPasteMode, terminal.paste() would
      // fire THREE separate onData events (\x1b[200~, text, \x1b[201~), each
      // becoming a separate WebSocket frame and PTY write. Claude Code's input
      // parser may not reassemble them correctly across separate reads.
      // ignoreBracketedPasteMode bypasses the wrapping for desktop paste
      // (Ctrl-V / Cmd-V), sending content as one atomic write instead.
      ignoreBracketedPasteMode: true,
    })

    const fitAddon = new FitAddon()
    // MED-9: only open http/https links — block file://, data:, javascript:, etc.
    const webLinksAddon = new WebLinksAddon((_event, uri) => {
      if (/^https?:\/\//i.test(uri)) {
        window.open(uri, '_blank', 'noopener,noreferrer')
      }
    })
    const unicode11Addon = new Unicode11Addon()

    term.loadAddon(fitAddon)
    term.loadAddon(webLinksAddon)
    term.loadAddon(unicode11Addon)
    term.unicode.activeVersion = '11'

    term.open(containerRef.current)
    fitAddon.fit()

    fitAddonRef.current = fitAddon
    setTerminal(term)  // triggers re-render → useTerminalSocket receives the instance

    return () => {
      term.dispose()
      setTerminal(null)
    }
  }, [])

  const handleDead = useCallback((reason: string) => {
    setIsDead(true)
    setDeadReason(reason)
  }, [])

  const { connected, sendInput, sendResize, reconnect } = useTerminalSocket({
    sessionId: session.id,
    terminal,
    onDead: handleDead,
  })

  useVisibilityReconnect({
    onBrowserReturn: reconnect,
    enabled: !isDead && !!terminal,
  })

  // Wire terminal input → WS
  useEffect(() => {
    if (!terminal) return
    const disposable = terminal.onData((data) => {
      sendInput(data)
    })
    return () => disposable.dispose()
  }, [terminal, sendInput])

  // ResizeObserver → fit + resize WS message
  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver(() => {
      const fitAddon = fitAddonRef.current
      if (!fitAddon || !terminal) return
      fitAddon.fit()
      sendResize(terminal.cols, terminal.rows)
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [sendResize])

  // Focus + refit when pane becomes active (important on mobile after un-hiding)
  useEffect(() => {
    if (isActive && terminal) {
      // Small delay lets the DOM finish showing the container before measuring
      const t = setTimeout(() => {
        fitAddonRef.current?.fit()
        sendResize(terminal.cols, terminal.rows)
        terminal.focus()
        if (isMobile) showSoftKeyboard()
      }, 50)
      return () => clearTimeout(t)
    }
  }, [isActive, terminal, isMobile, showSoftKeyboard, sendResize])

  // iOS Safari: visualViewport shrinks when the soft keyboard appears.
  // The ResizeObserver won't fire (our container's CSS size doesn't change),
  // so we watch visualViewport directly and refit after keyboard in/out.
  useEffect(() => {
    if (!isMobile || !window.visualViewport) return
    const vv = window.visualViewport
    const handleVVResize = () => {
      setTimeout(() => {
        fitAddonRef.current?.fit()
        if (terminal) sendResize(terminal.cols, terminal.rows)
      }, 50)
    }
    vv.addEventListener('resize', handleVVResize)
    return () => vv.removeEventListener('resize', handleVVResize)
  }, [isMobile, terminal, sendResize])

  const handleClick = () => {
    onClick()
    if (isMobile) showSoftKeyboard()
  }

  return (
    <div
      className={clsx(
        'relative flex flex-col rounded border overflow-hidden',
        isIdle ? 'animate-idle-pulse' :
        isActive ? 'border-terminal-active' : 'border-terminal-border',
        'bg-terminal-bg'
      )}
      onClick={handleClick}
    >
      {/* Title bar */}
      <div className={clsx(
        'flex items-center justify-between px-2 py-1 text-xs select-none',
        isIdle ? 'bg-amber-500/10' :
        isActive ? 'bg-terminal-active/20' : 'bg-[#161b22]'
      )}>
        <span className="font-mono truncate text-terminal-fg">{session.name}</span>
        <span className={clsx(
          'ml-2 shrink-0 rounded-full w-2 h-2',
          isIdle ? 'bg-amber-500 animate-pulse' :
          session.status === 'running' ? 'bg-green-500' :
          session.status === 'error' ? 'bg-red-500' :
          session.status === 'pending' ? 'bg-yellow-500' : 'bg-gray-500'
        )} />
      </div>

      {/* Mobile shortcut key strip — only rendered on touch devices for the active pane */}
      <MobileKeybar isVisible={isMobile && isActive} sendInput={sendInput} />

      {/* Terminal area */}
      <div ref={containerRef} className="flex-1 min-h-0 p-1" />

      {/* Dead overlay */}
      {isDead && (
        <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
          <div className="text-red-400 text-sm font-mono text-center p-4">
            <div className="text-lg mb-1">Session Ended</div>
            <div className="opacity-70">{deadReason}</div>
          </div>
        </div>
      )}

      {/* Connection indicator */}
      {!connected && !isDead && (
        <div className="absolute top-7 right-2 text-xs text-yellow-400 font-mono">connecting…</div>
      )}

      <MobileKeyboardShim
        terminal={terminal}
        inputRef={hiddenInputRef}
        isActive={isActive}
        sendInput={sendInput}
      />
    </div>
  )
}

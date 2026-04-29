import { useCallback, useEffect, useRef, useState } from 'react'
import type { Terminal } from '@xterm/xterm'
import { getWsToken } from '@/api/auth'
import type { WsFrame } from '@/types/ws'
import { toast } from '@/store/toastStore'
import { useSessionStore } from '@/store/sessionStore'

interface TerminalSocketOptions {
  sessionId: string
  terminal: Terminal | null
  onDead?: (reason: string) => void
}

const MAX_RETRIES = 3
const PING_INTERVAL_MS = 20_000
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

export function useTerminalSocket({ sessionId, terminal, onDead }: TerminalSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const replayRef = useRef(false)
  const [connected, setConnected] = useState(false)

  const cleanup = useCallback(() => {
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current)
      pingTimerRef.current = null
    }
  }, [])

  const connect = useCallback(async (replay = false) => {
    if (!UUID_RE.test(sessionId)) return
    try {
      let token: string
      try {
        token = await getWsToken(sessionId)
      } catch (err: unknown) {
        // If the session no longer exists (404) or we're not authenticated (401),
        // stop retrying — there's nothing to reconnect to.
        const status = (err as { response?: { status: number } }).response?.status
        if (status === 404 || status === 401) {
          onDead?.(`Session not available (${status})`)
          return
        }
        throw err
      }
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      // HIGH-3: pass the auth token as a Sec-WebSocket-Protocol subprotocol so
      // it never appears in the URL (browser history, proxy logs, Referrer headers).
      let url = `${protocol}://${window.location.host}/ws/session/${sessionId}`
      if (replay) url += '?replay=1'
      replayRef.current = replay
      const ws = new WebSocket(url, ['nexus-auth', token])
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        retriesRef.current = 0

        // On replay, clear stale content before buffer replay arrives
        if (replayRef.current && terminal) {
          terminal.reset()
        }

        // Sync PTY to the actual viewport size — send immediately AND after
        // a short delay (the FitAddon may not have measured yet at onopen time).
        const sendResize = () => {
          if (terminal && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }))
          }
        }
        sendResize()
        setTimeout(sendResize, 100)
        setTimeout(sendResize, 500)

        // Start ping loop
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }))
          }
        }, PING_INTERVAL_MS)
      }

      ws.onmessage = (evt: MessageEvent) => {
        try {
          const frame = JSON.parse(evt.data as string) as WsFrame
          if (frame.type === 'output' && terminal) {
            // Decode base64 output and write to terminal
            const bytes = Uint8Array.from(atob(frame.data), (c) => c.charCodeAt(0))
            terminal.write(bytes)
            useSessionStore.getState().markSessionOutput(sessionId)
          } else if (frame.type === 'session_dead') {
            // Mark max retries so onclose doesn't attempt reconnect
            retriesRef.current = MAX_RETRIES
            onDead?.(frame.reason)
            cleanup()
          } else if (frame.type === 'error') {
            terminal?.writeln(`\r\n\x1b[31m[Error: ${frame.message}]\x1b[0m\r\n`)
          }
        } catch {
          // ignore malformed frames
        }
      }

      ws.onclose = (evt) => {
        setConnected(false)
        cleanup()
        // Don't retry on auth failure (4401), not-found (4404), or session stopped (4410)
        const noRetry = evt.code === 4401 || evt.code === 4404 || evt.code === 4410
        if (retriesRef.current < MAX_RETRIES && !noRetry) {
          const delay = Math.pow(2, retriesRef.current) * 1000
          retriesRef.current += 1
          terminal?.writeln(`\r\n\x1b[33m[Reconnecting in ${delay / 1000}s...]\x1b[0m\r\n`)
          setTimeout(() => connect(), delay)
        } else if (evt.code === 4410) {
          onDead?.('Session stopped — use restart to resume')
        } else if (retriesRef.current >= MAX_RETRIES && !noRetry) {
          // Retries exhausted while tab may be backgrounded — don't call onDead.
          // The visibility hook will trigger reconnect when the user returns.
          terminal?.writeln(`\r\n\x1b[33m[Connection lost — will reconnect when tab is active]\x1b[0m\r\n`)
        }
      }

      ws.onerror = () => {
        // onclose will fire after onerror
      }
    } catch (err) {
      toast.error(`WebSocket error: ${err instanceof Error ? err.message : 'connection failed'}`)
    }
  }, [sessionId, terminal, onDead, cleanup])

  const reconnect = useCallback(() => {
    // Close stale WS if any
    cleanup()
    if (wsRef.current) {
      wsRef.current.onclose = null // prevent retry logic from firing
      wsRef.current.close()
      wsRef.current = null
    }
    // Reset retries and connect with replay
    retriesRef.current = 0
    connect(true)
  }, [connect, cleanup])

  const sendInput = useCallback((data: string) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data }))
    }
  }, [])

  const sendResize = useCallback((cols: number, rows: number) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols, rows }))
    }
  }, [])

  useEffect(() => {
    if (terminal) {
      connect()
    }
    return () => {
      cleanup()
      wsRef.current?.close()
    }
  }, [terminal, connect, cleanup])

  return { connected, sendInput, sendResize, reconnect }
}

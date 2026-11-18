import { useCallback, useEffect, useRef } from 'react'
import { useSessionStore } from '@/store/sessionStore'

interface KeyboardLock {
  lock?: (keys?: string[]) => Promise<void>
  unlock?: () => void
}

function keyboardApi(): KeyboardLock | undefined {
  return (navigator as Navigator & { keyboard?: KeyboardLock }).keyboard
}

/**
 * Full-screen ("immersive") mode: the app hides its own chrome — sidebar,
 * header, embedded page — so the shells get the whole window.
 *
 * Where the browser supports the Keyboard Lock API (Chromium desktop) it also
 * goes browser-fullscreen and locks Escape, so a quick Esc still reaches vim /
 * Claude Code and only *holding* Esc leaves fullscreen. Elsewhere (Safari,
 * Firefox, mobile) a plain Esc would exit browser fullscreen and be swallowed,
 * so there we only hide the app chrome and never touch the Fullscreen API.
 */
export function useFullscreen(isMobile: boolean) {
  const immersive = useSessionStore((s) => s.immersive)
  const setImmersive = useSessionStore((s) => s.setImmersive)
  const ownsBrowserFullscreen = useRef(false)

  const enter = useCallback(() => {
    setImmersive(true)
    const kb = keyboardApi()
    const el = document.documentElement
    if (isMobile || !kb?.lock || !el.requestFullscreen || document.fullscreenElement) return
    el.requestFullscreen()
      .then(() => {
        ownsBrowserFullscreen.current = true
        return kb.lock?.(['Escape'])
      })
      .catch(() => { /* denied or unsupported — app-level full screen still applies */ })
  }, [isMobile, setImmersive])

  const exit = useCallback(() => {
    setImmersive(false)
    if (ownsBrowserFullscreen.current && document.fullscreenElement) {
      keyboardApi()?.unlock?.()
      document.exitFullscreen().catch(() => {})
    }
    ownsBrowserFullscreen.current = false
  }, [setImmersive])

  const toggle = useCallback(() => {
    if (useSessionStore.getState().immersive) exit()
    else enter()
  }, [enter, exit])

  // Leaving browser fullscreen by the browser's own gesture (holding Esc, F11)
  // is a clear "get me out" — drop the app-level full screen with it.
  useEffect(() => {
    const onChange = () => {
      if (!document.fullscreenElement && ownsBrowserFullscreen.current) {
        ownsBrowserFullscreen.current = false
        keyboardApi()?.unlock?.()
        setImmersive(false)
      }
    }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [setImmersive])

  return { immersive, enter, exit, toggle }
}

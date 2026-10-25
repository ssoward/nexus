import { useEffect, type RefObject } from 'react'

/**
 * Takes over every clipboard paste inside the terminal container (desktop
 * Cmd/Ctrl+V, right-click paste, mobile long-press on xterm's textarea) in the
 * capture phase, before xterm's own handler sees it, and hands the plain text
 * to `paste` — so all sources share one path (see components/terminal/paste.ts).
 */
export function usePasteCapture(
  containerRef: RefObject<HTMLElement | null>,
  paste: (text: string) => void,
) {
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onPaste = (e: ClipboardEvent) => {
      e.preventDefault()
      e.stopPropagation()
      paste(e.clipboardData?.getData('text/plain') ?? '')
    }
    el.addEventListener('paste', onPaste, true)
    return () => el.removeEventListener('paste', onPaste, true)
  }, [containerRef, paste])
}

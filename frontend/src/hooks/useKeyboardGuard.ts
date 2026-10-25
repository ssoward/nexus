import { useCallback, useEffect, useRef } from 'react'

export function useKeyboardGuard() {
  const isMobile = typeof navigator !== 'undefined' && navigator.maxTouchPoints > 1
  const hiddenInputRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    if (!isMobile) return
    // A textarea, not an <input>: a single-line input strips the newlines out
    // of a multi-line long-press paste before we ever see it.
    const input = document.createElement('textarea')
    input.rows = 1
    input.inputMode = 'text'
    input.autocomplete = 'off'
    input.setAttribute('autocorrect', 'off')
    input.setAttribute('autocapitalize', 'off')
    input.setAttribute('spellcheck', 'false')
    input.style.cssText =
      'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;pointer-events:none;z-index:-1;'
    document.body.appendChild(input)
    hiddenInputRef.current = input
    return () => {
      document.body.removeChild(input)
    }
  }, [isMobile])

  const showSoftKeyboard = useCallback(() => {
    if (isMobile && hiddenInputRef.current) {
      hiddenInputRef.current.focus({ preventScroll: true })
    }
  }, [isMobile])

  return { isMobile, hiddenInputRef, showSoftKeyboard }
}

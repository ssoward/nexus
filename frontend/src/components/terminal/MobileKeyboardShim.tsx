import { useEffect, type RefObject } from 'react'
import type { Terminal } from '@xterm/xterm'

interface Props {
  terminal: Terminal | null
  inputRef: RefObject<HTMLInputElement | null>
  isActive: boolean
}

/**
 * Forwards events from a hidden <input> (which triggers the OS soft keyboard)
 * to the xterm.js Terminal instance.
 */
export function MobileKeyboardShim({ terminal, inputRef, isActive }: Props) {
  useEffect(() => {
    const input = inputRef.current
    if (!input || !terminal) return

    const onInput = (evt: Event) => {
      const e = evt as InputEvent
      if (e.data) {
        terminal.paste(e.data)
      }
      // Clear the hidden input so repeated chars work
      ;(evt.target as HTMLInputElement).value = ''
    }

    const onKeydown = (evt: KeyboardEvent) => {
      // Forward special keys that InputEvent doesn't capture
      const specialKeys: Record<string, string> = {
        Enter: '\r',
        Backspace: '\x7f',
        Tab: '\t',
        Escape: '\x1b',
        ArrowUp: '\x1b[A',
        ArrowDown: '\x1b[B',
        ArrowRight: '\x1b[C',
        ArrowLeft: '\x1b[D',
      }
      const mapped = specialKeys[evt.key]
      if (mapped) {
        evt.preventDefault()
        terminal.paste(mapped)
      } else if (evt.ctrlKey && evt.key.length === 1) {
        const code = evt.key.charCodeAt(0) - 96
        if (code > 0 && code < 27) {
          terminal.paste(String.fromCharCode(code))
          evt.preventDefault()
        }
      }
    }

    input.addEventListener('input', onInput)
    input.addEventListener('keydown', onKeydown)
    return () => {
      input.removeEventListener('input', onInput)
      input.removeEventListener('keydown', onKeydown)
    }
  }, [terminal, inputRef, isActive])

  return null
}

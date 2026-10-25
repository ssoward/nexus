import { useEffect, type RefObject } from 'react'
import type { Terminal } from '@xterm/xterm'

interface Props {
  terminal: Terminal | null
  inputRef: RefObject<HTMLTextAreaElement | null>
  isActive: boolean
  sendInput: (data: string) => void
  onPaste: (text: string) => void
}

/**
 * Forwards events from a hidden <textarea> (which triggers the OS soft
 * keyboard) to the PTY.
 *
 * Typed characters and special keys go straight to sendInput(). Pastes go
 * through onPaste (pasteToTerminal), which bracket-wraps them when the app
 * enabled bracketed paste so a multi-line paste is not submitted line by line.
 */
export function MobileKeyboardShim({ terminal, inputRef, isActive, sendInput, onPaste }: Props) {
  useEffect(() => {
    const input = inputRef.current
    if (!input || !terminal) return

    const onInput = (evt: Event) => {
      const e = evt as InputEvent
      const inputEl = evt.target as HTMLTextAreaElement
      if (e.inputType === 'insertFromPaste') {
        // e.data can be null on iOS Safari for paste — read full value instead.
        onPaste(inputEl.value)
      } else if (e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') {
        // Android keyboards often report Enter only as an input event
        // (keydown key "Unidentified"), which in a textarea inserts a newline.
        sendInput('\r')
      } else if (e.data) {
        sendInput(e.data)
      }
      // Clear so repeated chars and subsequent pastes work
      inputEl.value = ''
    }

    const onKeydown = (evt: KeyboardEvent) => {
      // Forward special keys that InputEvent doesn't capture.
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
        sendInput(mapped)
      } else if (evt.ctrlKey && evt.key.length === 1) {
        const code = evt.key.charCodeAt(0) - 96
        if (code > 0 && code < 27) {
          sendInput(String.fromCharCode(code))
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
  }, [terminal, inputRef, isActive, sendInput, onPaste])

  return null
}

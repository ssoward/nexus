import { useEffect, type RefObject } from 'react'
import type { Terminal } from '@xterm/xterm'

interface Props {
  terminal: Terminal | null
  inputRef: RefObject<HTMLInputElement | null>
  isActive: boolean
  sendInput: (data: string) => void
}

/**
 * Forwards events from a hidden <input> (which triggers the OS soft keyboard)
 * to the xterm.js Terminal instance.
 *
 * ALL paths use sendInput() directly to bypass bracketedPaste wrapping.
 * When Claude Code enables bracketedPasteMode, terminal.paste() fires three
 * separate onData events (\x1b[200~, text, \x1b[201~), producing three
 * WebSocket frames and three PTY writes. Claude Code may not reassemble them
 * correctly. sendInput() delivers content as one atomic PTY write.
 */
export function MobileKeyboardShim({ terminal, inputRef, isActive, sendInput }: Props) {
  useEffect(() => {
    const input = inputRef.current
    if (!input || !terminal) return

    const onInput = (evt: Event) => {
      const e = evt as InputEvent
      const inputEl = evt.target as HTMLInputElement
      if (e.inputType === 'insertFromPaste') {
        // e.data can be null on iOS Safari for paste — read full value instead.
        // Use sendInput (not terminal.paste) to deliver as one atomic PTY write,
        // bypassing bracketedPaste fragmentation.
        const text = inputEl.value
        if (text) sendInput(text)
      } else if (e.data) {
        // Regular typed characters — send directly to bypass paste wrapping
        sendInput(e.data)
      }
      // Clear so repeated chars and subsequent pastes work
      inputEl.value = ''
    }

    const onKeydown = (evt: KeyboardEvent) => {
      // Forward special keys that InputEvent doesn't capture.
      // Use sendInput (not terminal.paste) to avoid bracketedPaste wrapping.
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
  }, [terminal, inputRef, isActive, sendInput])

  return null
}

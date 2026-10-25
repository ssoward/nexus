import type { Terminal } from '@xterm/xterm'
import { toast } from '@/store/toastStore'

/** Largest paste the backend accepts as one input frame (rate_limiter.MAX_INPUT_CHARS). */
export const MAX_PASTE_CHARS = 256_000

// Bracketed-paste start/end markers. An end marker inside the clipboard would
// close the bracket early and let the rest of the text run as typed input.
// eslint-disable-next-line no-control-regex
const PASTE_MARKERS = /\x1b\[20[01]~/g

/**
 * Turn clipboard text into what a real terminal would send: newlines become
 * CR, and when the app has enabled bracketed paste (Claude Code, zsh, vim) the
 * text is wrapped so the app treats it as one paste rather than lines typed
 * one by one — otherwise each newline would submit a partial prompt.
 */
export function preparePaste(text: string, bracketed: boolean): string {
  const body = text.replace(PASTE_MARKERS, '').replace(/\r?\n/g, '\r')
  return bracketed ? `\x1b[200~${body}\x1b[201~` : body
}

/**
 * The single paste path for every input source (desktop Cmd/Ctrl+V, mobile
 * long-press, the keybar Paste button). Sent as ONE input frame so the PTY
 * receives the bracket markers and body in a single write.
 */
export function pasteToTerminal(
  terminal: Terminal | null,
  sendInput: (data: string) => void,
  text: string,
): boolean {
  if (!text) return false
  if (text.length > MAX_PASTE_CHARS) {
    toast.warning(
      `Paste too large (${text.length.toLocaleString()} chars, max ${MAX_PASTE_CHARS.toLocaleString()}) — not sent`,
    )
    return false
  }
  sendInput(preparePaste(text, terminal?.modes.bracketedPasteMode ?? false))
  return true
}

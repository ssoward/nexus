import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Terminal } from '@xterm/xterm'
import { preparePaste, pasteToTerminal, MAX_PASTE_CHARS } from './paste'
import { useToastStore } from '@/store/toastStore'

const term = (bracketedPasteMode: boolean) => ({ modes: { bracketedPasteMode } }) as unknown as Terminal

describe('preparePaste', () => {
  it('converts LF and CRLF to CR like a real terminal', () => {
    expect(preparePaste('a\nb\r\nc', false)).toBe('a\rb\rc')
  })

  it('wraps in bracketed-paste markers when the app enabled them', () => {
    expect(preparePaste('a\nb', true)).toBe('\x1b[200~a\rb\x1b[201~')
  })

  it('strips embedded markers so pasted text cannot escape the bracket', () => {
    const evil = 'harmless\x1b[201~rm -rf ~\n\x1b[200~'
    expect(preparePaste(evil, true)).toBe('\x1b[200~harmlessrm -rf ~\r\x1b[201~')
  })
})

describe('pasteToTerminal', () => {
  beforeEach(() => useToastStore.setState({ toasts: [] } as never))

  it('sends a multi-line paste bracketed, as ONE frame, when the app uses bracketed paste', () => {
    const sendInput = vi.fn()
    expect(pasteToTerminal(term(true), sendInput, 'line 1\nline 2\n')).toBe(true)
    expect(sendInput).toHaveBeenCalledTimes(1)
    expect(sendInput).toHaveBeenCalledWith('\x1b[200~line 1\rline 2\r\x1b[201~')
  })

  it('sends unbracketed when the app has not enabled bracketed paste', () => {
    const sendInput = vi.fn()
    pasteToTerminal(term(false), sendInput, 'echo hi\n')
    expect(sendInput).toHaveBeenCalledWith('echo hi\r')
  })

  it('treats a missing terminal as unbracketed', () => {
    const sendInput = vi.fn()
    pasteToTerminal(null, sendInput, 'x')
    expect(sendInput).toHaveBeenCalledWith('x')
  })

  it('ignores empty pastes', () => {
    const sendInput = vi.fn()
    expect(pasteToTerminal(term(true), sendInput, '')).toBe(false)
    expect(sendInput).not.toHaveBeenCalled()
  })

  it('refuses oversized pastes with a visible warning instead of a silent drop', () => {
    const sendInput = vi.fn()
    expect(pasteToTerminal(term(true), sendInput, 'x'.repeat(MAX_PASTE_CHARS + 1))).toBe(false)
    expect(sendInput).not.toHaveBeenCalled()
    expect(useToastStore.getState().toasts.some((t) => /too large/.test(t.message))).toBe(true)
  })

  it('accepts a paste right at the limit', () => {
    const sendInput = vi.fn()
    expect(pasteToTerminal(term(false), sendInput, 'x'.repeat(MAX_PASTE_CHARS))).toBe(true)
  })
})

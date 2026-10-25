import { render } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createRef } from 'react'
import { MobileKeyboardShim } from './MobileKeyboardShim'
import type { Terminal } from '@xterm/xterm'

function makeTerminal() {
  return { paste: vi.fn() } as unknown as Terminal
}

function setup(terminalOverride?: Terminal | null) {
  const inputEl = document.createElement('textarea')
  document.body.appendChild(inputEl)
  const inputRef = createRef<HTMLTextAreaElement>()
  // @ts-expect-error — assigning to readonly ref for test
  inputRef.current = inputEl

  const terminal = terminalOverride !== undefined ? terminalOverride : makeTerminal()
  const sendInput = vi.fn()
  const onPaste = vi.fn()

  render(
    <MobileKeyboardShim
      terminal={terminal}
      inputRef={inputRef}
      isActive={true}
      sendInput={sendInput}
      onPaste={onPaste}
    />
  )

  return { inputEl, terminal, sendInput, onPaste }
}

describe('MobileKeyboardShim', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Enter key (the bracketed-paste bug) ────────────────────────────────────
  it('sends \\r via sendInput for Enter — not terminal.paste', () => {
    const { inputEl, terminal, sendInput } = setup()
    fireEvent.keyDown(inputEl, { key: 'Enter' })
    expect(sendInput).toHaveBeenCalledWith('\r')
    expect((terminal as ReturnType<typeof makeTerminal>).paste).not.toHaveBeenCalled()
  })

  // ── Other special keys ─────────────────────────────────────────────────────
  it('sends escape sequence via sendInput for arrow keys', () => {
    const { inputEl, sendInput } = setup()
    fireEvent.keyDown(inputEl, { key: 'ArrowUp' })
    expect(sendInput).toHaveBeenCalledWith('\x1b[A')
    fireEvent.keyDown(inputEl, { key: 'ArrowDown' })
    expect(sendInput).toHaveBeenCalledWith('\x1b[B')
  })

  it('sends DEL via sendInput for Backspace', () => {
    const { inputEl, sendInput } = setup()
    fireEvent.keyDown(inputEl, { key: 'Backspace' })
    expect(sendInput).toHaveBeenCalledWith('\x7f')
  })

  it('sends Ctrl sequences via sendInput', () => {
    const { inputEl, sendInput } = setup()
    fireEvent.keyDown(inputEl, { key: 'c', ctrlKey: true })
    expect(sendInput).toHaveBeenCalledWith('\x03') // ^C = char 3
  })

  // ── Regular typed characters ───────────────────────────────────────────────
  it('sends typed characters via sendInput', () => {
    const { inputEl, sendInput } = setup()
    // Simulate an InputEvent for a normal keystroke
    const evt = new InputEvent('input', { inputType: 'insertText', data: 'a', bubbles: true })
    Object.defineProperty(inputEl, 'value', { value: 'a', configurable: true, writable: true })
    inputEl.dispatchEvent(evt)
    expect(sendInput).toHaveBeenCalledWith('a')
  })

  // ── Paste goes through the shared paste path (bracketing, size check) ─────
  it('routes insertFromPaste events to onPaste with the full multi-line value', () => {
    const { inputEl, terminal, sendInput, onPaste } = setup()
    Object.defineProperty(inputEl, 'value', { value: 'line one\nline two', configurable: true, writable: true })
    const evt = new InputEvent('input', { inputType: 'insertFromPaste', bubbles: true })
    inputEl.dispatchEvent(evt)
    expect(onPaste).toHaveBeenCalledWith('line one\nline two')
    expect(sendInput).not.toHaveBeenCalled()
    expect((terminal as ReturnType<typeof makeTerminal>).paste).not.toHaveBeenCalled()
  })

  it('sends \\r for Enter reported only as an insertLineBreak input event (Android)', () => {
    const { inputEl, sendInput } = setup()
    inputEl.dispatchEvent(new InputEvent('input', { inputType: 'insertLineBreak', bubbles: true }))
    expect(sendInput).toHaveBeenCalledWith('\r')
    expect(inputEl.value).toBe('')
  })

  // ── Null terminal — no crash ───────────────────────────────────────────────
  it('does not throw when terminal is null', () => {
    const { inputEl, sendInput } = setup(null)
    expect(() => fireEvent.keyDown(inputEl, { key: 'Enter' })).not.toThrow()
    expect(sendInput).not.toHaveBeenCalled()
  })
})

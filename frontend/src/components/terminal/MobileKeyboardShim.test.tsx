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
  const inputEl = document.createElement('input')
  document.body.appendChild(inputEl)
  const inputRef = createRef<HTMLInputElement>()
  // @ts-expect-error — assigning to readonly ref for test
  inputRef.current = inputEl

  const terminal = terminalOverride !== undefined ? terminalOverride : makeTerminal()
  const sendInput = vi.fn()

  render(
    <MobileKeyboardShim
      terminal={terminal}
      inputRef={inputRef}
      isActive={true}
      sendInput={sendInput}
    />
  )

  return { inputEl, terminal, sendInput }
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

  // ── Actual paste goes through terminal.paste (bracketedPaste should apply) ─
  it('routes insertFromPaste events through terminal.paste, not sendInput', () => {
    const { inputEl, terminal, sendInput } = setup()
    Object.defineProperty(inputEl, 'value', { value: 'pasted text', configurable: true, writable: true })
    const evt = new InputEvent('input', { inputType: 'insertFromPaste', bubbles: true })
    inputEl.dispatchEvent(evt)
    expect((terminal as ReturnType<typeof makeTerminal>).paste).toHaveBeenCalledWith('pasted text')
    expect(sendInput).not.toHaveBeenCalled()
  })

  // ── Null terminal — no crash ───────────────────────────────────────────────
  it('does not throw when terminal is null', () => {
    const { inputEl, sendInput } = setup(null)
    expect(() => fireEvent.keyDown(inputEl, { key: 'Enter' })).not.toThrow()
    expect(sendInput).not.toHaveBeenCalled()
  })
})

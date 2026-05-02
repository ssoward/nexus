import { useCallback } from 'react'
import type { Terminal } from '@xterm/xterm'
import { useVoiceInput } from '@/hooks/useVoiceInput'
import { toast } from '@/store/toastStore'

interface KeyDef {
  label: string
  title: string
  seq: string
}

/**
 * Ordered by frequency-of-use: Tab and ^C first (no-scroll visible),
 * arrows next, then less-common Ctrl combos.
 */
const KEYS: KeyDef[] = [
  { label: 'Tab',  title: 'Tab – autocomplete',        seq: '\t'     },
  { label: '^C',   title: 'Ctrl+C – interrupt',        seq: '\x03'   },
  { label: '↑',    title: 'Arrow Up – history prev',   seq: '\x1b[A' },
  { label: '↓',    title: 'Arrow Down – history next', seq: '\x1b[B' },
  { label: '←',    title: 'Arrow Left',                seq: '\x1b[D' },
  { label: '→',    title: 'Arrow Right',               seq: '\x1b[C' },
  { label: 'ESC',  title: 'Escape',                    seq: '\x1b'   },
  { label: '^D',   title: 'Ctrl+D – EOF / exit',       seq: '\x04'   },
  { label: '^L',   title: 'Ctrl+L – clear screen',     seq: '\x0c'   },
  { label: '^Z',   title: 'Ctrl+Z – suspend',          seq: '\x1a'   },
  { label: '^A',   title: 'Ctrl+A – start of line',    seq: '\x01'   },
  { label: '^E',   title: 'Ctrl+E – end of line',      seq: '\x05'   },
  { label: '^R',   title: 'Ctrl+R – history search',   seq: '\x12'   },
  { label: '|',    title: 'Pipe',                      seq: '|'      },
  { label: '~',    title: 'Tilde (home dir)',           seq: '~'      },
]

interface Props {
  terminal: Terminal | null
  isVisible: boolean
  sendInput: (data: string) => void
}

/**
 * A thin horizontal strip of quick-send buttons for mobile users who lack a
 * physical keyboard.  Uses onPointerDown + e.preventDefault() so the button
 * never steals focus away from the hidden keyboard-guard input.
 */
export function MobileKeybar({ terminal, isVisible, sendInput }: Props) {
  // Voice transcripts are genuine paste content — terminal.paste() is correct here
  const handleTranscript = useCallback(
    (text: string) => terminal?.paste(text),
    [terminal]
  )
  const { isListening, isSupported, toggle: toggleVoice } = useVoiceInput(handleTranscript)

  if (!isVisible) return null

  const send = (e: React.PointerEvent, seq: string) => {
    e.preventDefault() // keep focus on the hidden <input> — do NOT steal it
    // Use sendInput directly to bypass bracketedPaste wrapping for control sequences
    sendInput(seq)
  }

  const handlePaste = async (e: React.PointerEvent) => {
    e.preventDefault()
    try {
      const text = await navigator.clipboard.readText()
      if (text) terminal?.paste(text)
      else toast.warning('Clipboard is empty')
    } catch {
      toast.warning('Clipboard access denied — use long-press paste instead')
    }
  }

  const handleVoice = (e: React.PointerEvent) => {
    e.preventDefault()
    toggleVoice()
  }

  const btnClass =
    'shrink-0 min-w-[40px] h-8 px-2 text-xs font-mono rounded border border-terminal-border bg-[#161b22] text-terminal-fg/70 active:bg-terminal-active/20 active:text-terminal-fg select-none'

  const micClass = isListening
    ? 'shrink-0 min-w-[40px] h-8 px-2 text-xs font-mono rounded border border-red-700 bg-red-900/40 text-red-400 select-none animate-pulse'
    : btnClass

  return (
    <div
      className="shrink-0 flex overflow-x-auto no-scrollbar bg-[#0d1117] border-b border-terminal-border px-1 py-[3px] gap-[3px]"
      style={{ WebkitOverflowScrolling: 'touch' } as React.CSSProperties}
    >
      {/* Fixed-sequence keys */}
      {KEYS.slice(0, 2).map(({ label, title, seq }) => (
        <button
          key={label}
          title={title}
          onPointerDown={(e) => send(e, seq)}
          className={btnClass}
          style={{ touchAction: 'manipulation' }}
        >
          {label}
        </button>
      ))}

      {/* Paste — reads live clipboard content */}
      <button
        title="Paste from clipboard"
        onPointerDown={handlePaste}
        className={btnClass}
        style={{ touchAction: 'manipulation' }}
      >
        Paste
      </button>

      {/* Voice-to-text — only shown when browser supports SpeechRecognition */}
      {isSupported && (
        <button
          title={isListening ? 'Stop recording' : 'Voice input — speak a command'}
          onPointerDown={handleVoice}
          className={micClass}
          style={{ touchAction: 'manipulation' }}
        >
          {isListening ? 'Stop' : 'Mic'}
        </button>
      )}

      {/* Remaining fixed-sequence keys */}
      {KEYS.slice(2).map(({ label, title, seq }) => (
        <button
          key={label}
          title={title}
          onPointerDown={(e) => send(e, seq)}
          className={btnClass}
          style={{ touchAction: 'manipulation' }}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

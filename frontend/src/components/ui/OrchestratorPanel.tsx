import { useCallback, useEffect, useState } from 'react'
import { getAllSessionStates, sendSessionInput, type SessionState } from '@/api/orchestration'
import { toast } from '@/store/toastStore'
import { HelpTooltip } from './HelpTooltip'
import { useVoiceInput } from '@/hooks/useVoiceInput'

const STATE_COLORS: Record<string, string> = {
  WORKING: 'bg-blue-900/40 text-blue-400 border-blue-700',
  WAITING: 'bg-green-900/40 text-green-400 border-green-700',
  ASKING: 'bg-amber-900/40 text-amber-400 border-amber-700',
  BUSY: 'bg-gray-900/40 text-gray-400 border-gray-700',
}

const HISTORY_KEY = 'nexus_cmd_history'
const MAX_HISTORY = 20

function loadHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]')
  } catch {
    return []
  }
}

function saveHistory(history: string[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
}

interface Props {
  onClose?: () => void
}

export function OrchestratorPanel({ onClose }: Props) {
  const [states, setStates] = useState<SessionState[]>([])
  const [batchInput, setBatchInput] = useState('')
  const [sendTargetId, setSendTargetId] = useState<string | null>(null)
  const [singleInput, setSingleInput] = useState('')
  const [cmdHistory, setCmdHistory] = useState<string[]>(loadHistory)

  const addToHistory = useCallback((cmd: string) => {
    const trimmed = cmd.trim()
    if (!trimmed) return
    setCmdHistory((prev) => {
      const next = [trimmed, ...prev.filter((h) => h !== trimmed)].slice(0, MAX_HISTORY)
      saveHistory(next)
      return next
    })
  }, [])

  const batchVoice = useVoiceInput(
    useCallback((text: string) => setBatchInput((p) => (p ? p + ' ' : '') + text), [])
  )
  const singleVoice = useVoiceInput(
    useCallback((text: string) => setSingleInput((p) => (p ? p + ' ' : '') + text), [])
  )

  const refresh = useCallback(async () => {
    try {
      setStates(await getAllSessionStates())
    } catch {
      // silently fail — user may not have sessions
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [refresh])

  const handleBatchSend = async () => {
    if (!batchInput.trim()) return
    const waiting = states.filter((s) => s.state === 'WAITING')
    if (waiting.length === 0) {
      toast.warning('No WAITING sessions')
      return
    }
    for (const s of waiting) {
      try {
        await sendSessionInput(s.session_id, batchInput)
      } catch {
        toast.error(`Failed to send to ${s.name}`)
      }
    }
    addToHistory(batchInput)
    toast.success(`Sent to ${waiting.length} session(s)`)
    setBatchInput('')
    refresh()
  }

  const handleSingleSend = async (sessionId: string) => {
    if (!singleInput.trim()) return
    try {
      await sendSessionInput(sessionId, singleInput)
      addToHistory(singleInput)
      toast.success('Sent')
      setSingleInput('')
      setSendTargetId(null)
      refresh()
    } catch {
      toast.error('Failed to send')
    }
  }

  const micBtnClass = (listening: boolean) =>
    listening
      ? 'px-2 py-1 text-[10px] font-mono rounded border border-red-700 bg-red-900/40 text-red-400 animate-pulse'
      : 'px-2 py-1 text-[10px] font-mono rounded border border-terminal-border text-terminal-fg/50 hover:bg-terminal-border'

  return (
    <aside className="w-full h-full flex flex-col bg-[#0d1117] border-r border-terminal-border">
      <div className="flex items-center justify-between px-3 py-2 border-b border-terminal-border shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-mono text-terminal-fg/60 uppercase tracking-wider">Orchestrator</span>
          <HelpTooltip
            text="Monitor and send input to all running sessions. Use this to unblock parallel Claude Code agents or automate multi-session workflows."
            side="below"
          />
        </div>
        {onClose && (
          <button onClick={onClose} className="text-terminal-fg/40 hover:text-terminal-fg p-1 rounded" aria-label="Close">
            ✕
          </button>
        )}
      </div>

      {/* State legend */}
      <div className="px-3 pt-2 pb-1 border-b border-terminal-border/50">
        <p className="text-[10px] font-mono text-terminal-fg/30 uppercase mb-1.5">Session States</p>
        <dl className="space-y-0.5">
          {[
            { state: 'WORKING', desc: 'Producing output right now' },
            { state: 'WAITING', desc: 'At a shell prompt — ready' },
            { state: 'ASKING',  desc: 'Waiting for y/n input' },
            { state: 'BUSY',    desc: 'Running, no prompt visible' },
          ].map(({ state, desc }) => (
            <div key={state} className="flex items-center gap-2">
              <span className={`text-[9px] font-mono px-1 py-0.5 rounded border ${STATE_COLORS[state]}`}>{state}</span>
              <span className="text-[10px] font-mono text-terminal-fg/40">{desc}</span>
            </div>
          ))}
        </dl>
      </div>

      {/* Batch send to WAITING */}
      <div className="px-3 py-2 border-b border-terminal-border/50">
        <div className="flex items-center gap-1.5 mb-1">
          <label className="text-[10px] font-mono text-terminal-fg/40 uppercase">Send to all WAITING</label>
          <HelpTooltip
            text="Types this text into every session currently at a shell prompt (WAITING state). Useful for unblocking multiple agents stuck on the same confirmation."
          />
        </div>
        <div className="flex gap-1">
          <input
            list="nexus-cmd-history"
            value={batchInput}
            onChange={(e) => setBatchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleBatchSend()}
            placeholder="command..."
            className="flex-1 px-2 py-1 text-xs font-mono bg-terminal-bg border border-terminal-border rounded text-terminal-fg"
          />
          {batchVoice.isSupported && (
            <button
              title={batchVoice.isListening ? 'Stop recording' : 'Voice input'}
              onClick={batchVoice.toggle}
              className={micBtnClass(batchVoice.isListening)}
            >
              {batchVoice.isListening ? '■' : 'Mic'}
            </button>
          )}
          <button
            onClick={handleBatchSend}
            className="px-2 py-1 text-xs font-mono rounded bg-terminal-active/20 hover:bg-terminal-active/40 text-terminal-active"
          >
            Send
          </button>
        </div>
        {/* Native browser datalist for history suggestions */}
        <datalist id="nexus-cmd-history">
          {cmdHistory.map((cmd) => (
            <option key={cmd} value={cmd} />
          ))}
        </datalist>
      </div>

      {/* Session states */}
      <div className="flex-1 overflow-y-auto">
        {states.length === 0 && (
          <p className="px-3 py-4 text-xs font-mono text-terminal-fg/30 text-center">No running sessions</p>
        )}
        {states.map((s) => (
          <div key={s.session_id} className="px-3 py-2 border-b border-terminal-border/50 hover:bg-white/5">
            <div className="flex items-center justify-between gap-1">
              <span className="text-sm font-mono text-terminal-fg truncate">{s.name}</span>
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${STATE_COLORS[s.state]}`}>
                {s.state}
              </span>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-[10px] font-mono text-terminal-fg/30">
                idle {s.idle_seconds.toFixed(0)}s
              </span>
              <button
                onClick={() => setSendTargetId(sendTargetId === s.session_id ? null : s.session_id)}
                className="text-[10px] font-mono text-terminal-active hover:underline"
              >
                send
              </button>
            </div>
            {sendTargetId === s.session_id && (
              <div className="flex gap-1 mt-1">
                <input
                  list="nexus-cmd-history"
                  value={singleInput}
                  onChange={(e) => setSingleInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSingleSend(s.session_id)}
                  placeholder="input..."
                  autoFocus
                  className="flex-1 px-2 py-1 text-xs font-mono bg-terminal-bg border border-terminal-border rounded text-terminal-fg"
                />
                {singleVoice.isSupported && (
                  <button
                    title={singleVoice.isListening ? 'Stop recording' : 'Voice input'}
                    onClick={singleVoice.toggle}
                    className={micBtnClass(singleVoice.isListening)}
                  >
                    {singleVoice.isListening ? '■' : 'Mic'}
                  </button>
                )}
                <button
                  onClick={() => handleSingleSend(s.session_id)}
                  className="px-2 py-1 text-xs font-mono rounded bg-terminal-active/20 text-terminal-active"
                >
                  ↵
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="px-3 py-2 border-t border-terminal-border shrink-0 space-y-1">
        <button onClick={refresh} className="w-full py-1 text-xs font-mono rounded border border-terminal-border text-terminal-fg/60 hover:bg-terminal-border">
          Refresh States
        </button>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => {
              navigator.clipboard.writeText('/mastermind')
              toast.success('Copied /mastermind — paste in Claude Code')
            }}
            className="flex-1 py-1 text-xs font-mono rounded border border-terminal-border text-terminal-fg/60 hover:bg-terminal-border"
          >
            Copy /mastermind Command
          </button>
          <HelpTooltip
            text="Mastermind is a Claude Code slash command that autonomously monitors all sessions, reads their terminal output, and decides what to type — repeating every 3 minutes via CronCreate. Paste it into any Claude Code session to start."
            side="above"
            width="w-64"
          />
        </div>
      </div>
    </aside>
  )
}

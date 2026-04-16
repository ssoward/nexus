interface Props {
  onClose: () => void
}

const SECTIONS = [
  {
    title: 'Sessions',
    items: [
      ['Create a session', 'Open the Sessions sidebar tab → click + New. Give it a name and pick a type. Up to 6 sessions can run at once.'],
      ['Session types', 'Bash / Zsh — login shell with your dotfiles. Claude Code — Claude AI assistant CLI. Python 3 — interactive REPL.'],
      ['Sessions survive disconnects', 'Closing the browser tab does not kill the terminal. The PTY process keeps running and the output buffer is preserved. Reconnect any time.'],
      ['Idle timeout', 'Sessions with no output for more than 1 hour are stopped automatically. Change idle_timeout_seconds in config.yml.'],
      ['Recovery', 'On clean shutdown, terminal buffers are saved to ~/.nexus/recovery.json and replayed on the next connect.'],
    ],
  },
  {
    title: 'Layouts',
    items: [
      ['Grid', 'All running sessions share equal space. Toggle via the grid icon in the header.'],
      ['Priority', '80 / 20 split: one large primary pane + thumbnail strips for the rest. Toggle via the priority icon in the header.'],
      ['Auto-promote', 'In Priority mode, the ▶ button automatically promotes the most recently active session to primary when the current primary goes idle.'],
    ],
  },
  {
    title: 'Terminal States (Orchestrator)',
    items: [
      ['WORKING', 'Terminal produced output in the last 3 seconds — a command is running.'],
      ['WAITING', 'Terminal is idle at a shell prompt ($ / # / >>> / irb>). Ready to receive the next command.'],
      ['ASKING', 'Terminal is waiting for a yes/no answer or confirmation (e.g. "Do you want to continue? (y/n)").'],
      ['BUSY', 'Terminal is idle but not at a recognized prompt — likely mid-output or paused.'],
    ],
  },
  {
    title: 'Orchestrator',
    items: [
      ['Send to all WAITING', 'Types the same input into every session currently in WAITING state. Useful for unblocking parallel agents that all hit a confirmation prompt.'],
      ['Per-session send', 'Click the "send" link next to any session to type directly into that session.'],
      ['Mastermind', 'An autonomous Claude Code slash command (/mastermind) that monitors all sessions, reads their buffers, and decides what to type. Copy it with the button and paste it into a Claude Code session to start autonomous orchestration.'],
      ['wctl.py', 'Command-line tool for scripting orchestration. See the README → wctl.py section for full usage.'],
    ],
  },
  {
    title: 'Pages',
    items: [
      ['Embedded pages', 'Open the Pages sidebar tab to add HTTPS URLs. They render as sandboxed iframes alongside your terminals (desktop only).'],
    ],
  },
  {
    title: 'Mobile',
    items: [
      ['Sidebar', 'Tap the hamburger icon to open the session drawer. Tap outside to dismiss.'],
      ['Keybar', 'A row of common keys (Tab, Ctrl+C, Paste, arrows) appears at the bottom of each terminal. Tap to send.'],
      ['Soft keyboard', 'Tap anywhere on the terminal to trigger the soft keyboard.'],
    ],
  },
  {
    title: 'Security',
    items: [
      ['2FA', 'Every login requires a TOTP code from your authenticator app (Google Authenticator, Authy, 1Password, etc.). Re-configure it via the lock icon in the header.'],
      ['Auto sign-out', 'Sessions expire after 60 minutes of inactivity. Active tabs refresh automatically every 30 minutes.'],
    ],
  },
]

export function HelpModal({ onClose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-start justify-center z-50 pt-16 px-4 overflow-y-auto">
      <div className="bg-[#161b22] border border-terminal-border rounded-lg w-full max-w-xl mb-8">
        <div className="flex items-center justify-between px-5 py-3 border-b border-terminal-border sticky top-0 bg-[#161b22] rounded-t-lg">
          <span className="font-mono text-sm text-terminal-fg">Nexus — Help</span>
          <button
            onClick={onClose}
            className="text-terminal-fg/40 hover:text-terminal-fg p-1 rounded"
            aria-label="Close help"
          >
            ✕
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          {SECTIONS.map((section) => (
            <div key={section.title}>
              <h3 className="text-[10px] font-mono text-terminal-fg/40 uppercase tracking-widest mb-2">
                {section.title}
              </h3>
              <dl className="space-y-2">
                {section.items.map(([term, def]) => (
                  <div key={term} className="grid grid-cols-[auto_1fr] gap-x-3 items-start">
                    <dt className="text-xs font-mono text-terminal-active whitespace-nowrap pt-0.5">{term}</dt>
                    <dd className="text-xs font-mono text-terminal-fg/70 leading-relaxed">{def}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>

        <div className="px-5 py-3 border-t border-terminal-border">
          <p className="text-[10px] font-mono text-terminal-fg/30">
            Full docs → README.md · CLI → <code className="text-terminal-fg/50">python3 wctl.py --help</code>
          </p>
        </div>
      </div>
    </div>
  )
}

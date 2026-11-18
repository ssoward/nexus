import { useSessionStore, type LayoutMode } from '@/store/sessionStore'

const MODES: { mode: LayoutMode; title: string; path: string }[] = [
  { mode: 'grid', title: 'Grid — all shells visible', path: 'M1 1h6v6H1zm8 0h6v6H9zM1 9h6v6H1zm8 0h6v6H9z' },
  { mode: 'priority', title: 'Priority — one large shell + thumbnails', path: 'M1 1h10v10H1zm12 0h2v4h-2zM13 6h2v5h-2z' },
  { mode: 'focus', title: 'Focus — one shell fills the area (Ctrl/Cmd Shift Enter)', path: 'M1 1h14v14H1zm1.5 3v9.5h11V4z' },
]

interface Props {
  /** Mobile is always one shell at a time, so focus mode adds nothing there. */
  showFocus?: boolean
}

/** Grid / Priority / Focus layout switcher, plus the auto-promote toggle in priority mode. */
export function LayoutControls({ showFocus = true }: Props) {
  const layoutMode = useSessionStore((s) => s.layoutMode)
  const setLayoutMode = useSessionStore((s) => s.setLayoutMode)
  const autoPromote = useSessionStore((s) => s.autoPromote)
  const setAutoPromote = useSessionStore((s) => s.setAutoPromote)

  return (
    <div className="flex items-center gap-0.5 shrink-0" role="group" aria-label="Layout">
      {MODES.filter((m) => showFocus || m.mode !== 'focus').map((m) => (
        <button
          key={m.mode}
          onClick={() => setLayoutMode(m.mode)}
          className={`p-1.5 rounded transition-colors ${layoutMode === m.mode ? 'text-terminal-active bg-terminal-active/10' : 'text-terminal-fg/40 hover:text-terminal-fg'}`}
          title={m.title}
          aria-label={`${m.mode} layout`}
          aria-pressed={layoutMode === m.mode}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" fillRule="evenodd">
            <path d={m.path} />
          </svg>
        </button>
      ))}
      {layoutMode === 'priority' && (
        <button
          onClick={() => setAutoPromote(!autoPromote)}
          className={`ml-1 p-1.5 rounded text-xs font-mono transition-colors ${autoPromote ? 'text-green-400 bg-green-900/20' : 'text-terminal-fg/40 bg-terminal-border/30'}`}
          title={autoPromote ? 'Auto-promote ON' : 'Auto-promote OFF'}
        >
          {autoPromote ? '▶' : '⏸'}
        </button>
      )}
    </div>
  )
}

interface FullscreenButtonProps {
  active: boolean
  onClick: () => void
}

/** Enter / exit full screen (hide sidebar + header). */
export function FullscreenButton({ active, onClick }: FullscreenButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`p-1.5 rounded transition-colors shrink-0 ${active ? 'text-terminal-active bg-terminal-active/10 hover:bg-terminal-active/20' : 'text-terminal-fg/40 hover:text-terminal-fg hover:bg-terminal-border'}`}
      title={active ? 'Exit full screen (Ctrl/Cmd Shift F)' : 'Full screen (Ctrl/Cmd Shift F)'}
      aria-label={active ? 'Exit full screen' : 'Full screen'}
      aria-pressed={active}
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
        {active
          ? <path d="M5.5 1v4.5H1V4h3V1zm5 0H12v3h3v1.5h-4.5zM1 10.5h4.5V15H4v-3H1zm9.5 0H15V12h-3v3h-1.5z" />
          : <path d="M1 1h4.5v1.5h-3v3H1zm9.5 0H15v4.5h-1.5v-3h-3zM1 10.5h1.5v3h3V15H1zm12.5 0H15V15h-4.5v-1.5h3z" />}
      </svg>
    </button>
  )
}

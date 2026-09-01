import {
  useDisplayStore,
  UI_SCALE_MIN,
  UI_SCALE_MAX,
} from '@/store/displayStore'

interface Props {
  /** Hide the percentage readout when horizontal space is tight (mobile header). */
  compact?: boolean
}

/**
 * A− / A+ zoom stepper for the header. Steps the whole UI and the terminal
 * font together; the percentage doubles as a reset button.
 */
export function DisplayScaleControls({ compact = false }: Props) {
  const uiScale = useDisplayStore((s) => s.uiScale)
  const step = useDisplayStore((s) => s.step)
  const reset = useDisplayStore((s) => s.reset)

  const btn =
    'px-1.5 py-1 rounded font-mono leading-none text-terminal-fg/50 hover:text-terminal-fg hover:bg-terminal-border transition-colors disabled:opacity-30 disabled:hover:bg-transparent'

  return (
    <div className="flex items-center shrink-0" role="group" aria-label="Display size">
      <button
        onClick={() => step(-1)}
        disabled={uiScale <= UI_SCALE_MIN}
        className={`${btn} text-xs`}
        title="Decrease display size (Ctrl/Cmd −)"
        aria-label="Decrease display size"
      >
        A−
      </button>
      {!compact && (
        <button
          onClick={reset}
          className="px-1 text-[0.625rem] font-mono text-terminal-fg/30 hover:text-terminal-fg tabular-nums"
          title="Reset display size (Ctrl/Cmd 0)"
          aria-label="Reset display size"
        >
          {Math.round(uiScale * 100)}%
        </button>
      )}
      <button
        onClick={() => step(1)}
        disabled={uiScale >= UI_SCALE_MAX}
        className={`${btn} text-base`}
        title="Increase display size (Ctrl/Cmd +)"
        aria-label="Increase display size"
      >
        A+
      </button>
    </div>
  )
}

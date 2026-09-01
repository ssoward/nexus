import { create } from 'zustand'

/**
 * Accessibility zoom for small screens.
 *
 * Two independent knobs, both stepped together by the header +/- buttons:
 *  - `uiScale`      multiplies the root font size, so every rem-based Tailwind
 *                   size (chrome text, buttons, paddings) scales with it.
 *  - `terminalFontSize`  xterm.js font size in px. xterm measures the glyph
 *                   cell itself and can't inherit a rem, so it's carried
 *                   separately and applied via `term.options.fontSize`.
 */
export const UI_SCALE_MIN = 0.8
export const UI_SCALE_MAX = 2.0
export const UI_SCALE_STEP = 0.1

export const TERM_FONT_MIN = 8
export const TERM_FONT_MAX = 28
export const TERM_FONT_STEP = 1

export const ROOT_FONT_PX = 16

const STORAGE_KEY = 'nexus.display'

/** Same touch/width heuristic as useIsMobile — phones start at a smaller cell. */
function defaultTerminalFontSize(): number {
  if (typeof window === 'undefined') return 14
  const coarse =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(pointer: coarse)').matches
  return coarse || window.innerWidth < 640 ? 10 : 14
}

const clamp = (v: number, min: number, max: number) =>
  Math.min(max, Math.max(min, v))

// Scale steps land on floats like 1.2000000000000002 otherwise, which then
// render as "120.00000000000001%" in the badge.
const round1 = (v: number) => Math.round(v * 10) / 10

interface Persisted {
  uiScale: number
  terminalFontSize: number
}

function load(): Persisted {
  const fallback = { uiScale: 1, terminalFontSize: defaultTerminalFontSize() }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<Persisted>
    return {
      uiScale:
        typeof parsed.uiScale === 'number'
          ? clamp(round1(parsed.uiScale), UI_SCALE_MIN, UI_SCALE_MAX)
          : fallback.uiScale,
      terminalFontSize:
        typeof parsed.terminalFontSize === 'number'
          ? clamp(Math.round(parsed.terminalFontSize), TERM_FONT_MIN, TERM_FONT_MAX)
          : fallback.terminalFontSize,
    }
  } catch {
    return fallback
  }
}

function save(state: Persisted) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Private-mode / quota failures are non-fatal — the zoom just won't persist.
  }
}

interface DisplayState extends Persisted {
  setUiScale: (v: number) => void
  setTerminalFontSize: (v: number) => void
  /** Step both knobs one notch in `dir` (+1 bigger, -1 smaller). */
  step: (dir: 1 | -1) => void
  reset: () => void
}

export const useDisplayStore = create<DisplayState>((set) => {
  const persist = (next: Persisted) => {
    save(next)
    return next
  }

  return {
    ...load(),

    setUiScale: (v) =>
      set((s) =>
        persist({
          uiScale: clamp(round1(v), UI_SCALE_MIN, UI_SCALE_MAX),
          terminalFontSize: s.terminalFontSize,
        })
      ),

    setTerminalFontSize: (v) =>
      set((s) =>
        persist({
          uiScale: s.uiScale,
          terminalFontSize: clamp(Math.round(v), TERM_FONT_MIN, TERM_FONT_MAX),
        })
      ),

    step: (dir) =>
      set((s) =>
        persist({
          uiScale: clamp(
            round1(s.uiScale + dir * UI_SCALE_STEP),
            UI_SCALE_MIN,
            UI_SCALE_MAX
          ),
          terminalFontSize: clamp(
            s.terminalFontSize + dir * TERM_FONT_STEP,
            TERM_FONT_MIN,
            TERM_FONT_MAX
          ),
        })
      ),

    reset: () =>
      set(() =>
        persist({ uiScale: 1, terminalFontSize: defaultTerminalFontSize() })
      ),
  }
})

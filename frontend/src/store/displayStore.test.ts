import { describe, it, expect, beforeEach } from 'vitest'
import {
  useDisplayStore,
  UI_SCALE_MIN,
  UI_SCALE_MAX,
  TERM_FONT_MIN,
  TERM_FONT_MAX,
} from './displayStore'

const set = useDisplayStore.setState

// This environment's global localStorage is not a usable Storage object, and
// jsdom has no matchMedia — stub both with the minimum the store touches.
const memStore = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (k: string) => memStore.get(k) ?? null,
    setItem: (k: string, v: string) => void memStore.set(k, v),
    removeItem: (k: string) => void memStore.delete(k),
    clear: () => memStore.clear(),
  },
})

// jsdom has no matchMedia; report a desktop (fine-pointer) device.
window.matchMedia = ((q: string) => ({
  matches: false,
  media: q,
  addEventListener() {},
  removeEventListener() {},
})) as unknown as typeof window.matchMedia

describe('displayStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useDisplayStore.getState().reset()
  })

  it('steps UI scale and terminal font together', () => {
    set({ uiScale: 1, terminalFontSize: 14 })
    useDisplayStore.getState().step(1)
    expect(useDisplayStore.getState().uiScale).toBe(1.1)
    expect(useDisplayStore.getState().terminalFontSize).toBe(15)

    useDisplayStore.getState().step(-1)
    expect(useDisplayStore.getState().uiScale).toBe(1)
    expect(useDisplayStore.getState().terminalFontSize).toBe(14)
  })

  it('keeps the scale readout free of float drift', () => {
    set({ uiScale: 1, terminalFontSize: 14 })
    for (let i = 0; i < 3; i++) useDisplayStore.getState().step(1)
    expect(useDisplayStore.getState().uiScale).toBe(1.3)
  })

  it('clamps both values to their bounds', () => {
    set({ uiScale: UI_SCALE_MAX, terminalFontSize: TERM_FONT_MAX })
    useDisplayStore.getState().step(1)
    expect(useDisplayStore.getState().uiScale).toBe(UI_SCALE_MAX)
    expect(useDisplayStore.getState().terminalFontSize).toBe(TERM_FONT_MAX)

    set({ uiScale: UI_SCALE_MIN, terminalFontSize: TERM_FONT_MIN })
    useDisplayStore.getState().step(-1)
    expect(useDisplayStore.getState().uiScale).toBe(UI_SCALE_MIN)
    expect(useDisplayStore.getState().terminalFontSize).toBe(TERM_FONT_MIN)
  })

  it('persists to localStorage', () => {
    useDisplayStore.getState().setUiScale(1.4)
    useDisplayStore.getState().setTerminalFontSize(20)
    expect(JSON.parse(localStorage.getItem('nexus.display')!)).toEqual({
      uiScale: 1.4,
      terminalFontSize: 20,
    })
  })

  it('reset returns to 100% and the device default font size', () => {
    useDisplayStore.getState().setUiScale(1.6)
    useDisplayStore.getState().reset()
    expect(useDisplayStore.getState().uiScale).toBe(1)
    expect(useDisplayStore.getState().terminalFontSize).toBe(14)
  })
})

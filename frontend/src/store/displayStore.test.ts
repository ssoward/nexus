import { describe, it, expect, beforeEach } from 'vitest'
import {
  useDisplayStore,
  UI_SCALE_MIN,
  UI_SCALE_MAX,
  UI_SCALE_STEP,
  TERM_FONT_MIN,
  TERM_FONT_MAX,
} from './displayStore'

const STORAGE_KEY = 'nexus.display'
const set = useDisplayStore.setState
const get = () => useDisplayStore.getState()

describe('displayStore', () => {
  beforeEach(() => {
    localStorage.clear()
    get().reset()
  })

  describe('step', () => {
    it('moves UI scale and terminal font together', () => {
      set({ uiScale: 1, terminalFontSize: 14 })

      get().step(1)
      expect(get().uiScale).toBe(1.1)
      expect(get().terminalFontSize).toBe(15)

      get().step(-1)
      expect(get().uiScale).toBe(1)
      expect(get().terminalFontSize).toBe(14)
    })

    it('keeps the percentage readout free of float drift', () => {
      set({ uiScale: 1, terminalFontSize: 14 })
      for (let i = 0; i < 3; i++) get().step(1)
      // 1 + 0.1*3 is 1.3000000000000003 without rounding, which renders as
      // "130.00000000000003%" in the header badge.
      expect(get().uiScale).toBe(1.3)
      expect(Math.round(get().uiScale * 100)).toBe(130)
    })

    it('never exceeds the upper bounds', () => {
      set({ uiScale: UI_SCALE_MAX, terminalFontSize: TERM_FONT_MAX })
      get().step(1)
      expect(get().uiScale).toBe(UI_SCALE_MAX)
      expect(get().terminalFontSize).toBe(TERM_FONT_MAX)
    })

    it('never drops below the lower bounds', () => {
      set({ uiScale: UI_SCALE_MIN, terminalFontSize: TERM_FONT_MIN })
      get().step(-1)
      expect(get().uiScale).toBe(UI_SCALE_MIN)
      expect(get().terminalFontSize).toBe(TERM_FONT_MIN)
    })

    it('walks the whole range without landing off-step', () => {
      set({ uiScale: UI_SCALE_MIN, terminalFontSize: TERM_FONT_MIN })
      const steps = Math.round((UI_SCALE_MAX - UI_SCALE_MIN) / UI_SCALE_STEP)
      for (let i = 0; i < steps; i++) get().step(1)
      expect(get().uiScale).toBe(UI_SCALE_MAX)
    })
  })

  describe('setters', () => {
    it('clamps an out-of-range UI scale', () => {
      get().setUiScale(99)
      expect(get().uiScale).toBe(UI_SCALE_MAX)
      get().setUiScale(-5)
      expect(get().uiScale).toBe(UI_SCALE_MIN)
    })

    it('clamps and rounds an out-of-range font size', () => {
      get().setTerminalFontSize(999)
      expect(get().terminalFontSize).toBe(TERM_FONT_MAX)
      get().setTerminalFontSize(0)
      expect(get().terminalFontSize).toBe(TERM_FONT_MIN)
      get().setTerminalFontSize(15.7)
      expect(get().terminalFontSize).toBe(16)
    })

    it('changes one knob without disturbing the other', () => {
      set({ uiScale: 1.2, terminalFontSize: 18 })
      get().setUiScale(1.5)
      expect(get().terminalFontSize).toBe(18)
      get().setTerminalFontSize(11)
      expect(get().uiScale).toBe(1.5)
    })
  })

  describe('persistence', () => {
    it('writes both values to localStorage', () => {
      get().setUiScale(1.4)
      get().setTerminalFontSize(20)
      expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toEqual({
        uiScale: 1.4,
        terminalFontSize: 20,
      })
    })

    it('persists on step and on reset too', () => {
      get().step(1)
      expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).uiScale).toBe(1.1)
      get().reset()
      expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).uiScale).toBe(1)
    })

    it('survives a write failure (private mode / quota) without throwing', () => {
      const original = localStorage.setItem
      localStorage.setItem = () => {
        throw new Error('QuotaExceededError')
      }
      expect(() => get().setUiScale(1.5)).not.toThrow()
      // In-memory state still updates even though it could not be saved.
      expect(get().uiScale).toBe(1.5)
      localStorage.setItem = original
    })
  })

  describe('reset', () => {
    it('returns to 100% and the device-default font size', () => {
      get().setUiScale(1.6)
      get().setTerminalFontSize(24)
      get().reset()
      expect(get().uiScale).toBe(1)
      // matchMedia is stubbed to a fine-pointer device in the test setup.
      expect(get().terminalFontSize).toBe(14)
    })
  })
})

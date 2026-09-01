import { describe, it, expect, beforeEach, vi } from 'vitest'
import { UI_SCALE_MAX, TERM_FONT_MIN } from './displayStore'

const STORAGE_KEY = 'nexus.display'

/** Re-import the store fresh so its module-scope hydration runs again. */
async function freshStore(seed: string | null) {
  localStorage.clear()
  if (seed !== null) localStorage.setItem(STORAGE_KEY, seed)
  vi.resetModules()
  const mod = await import('./displayStore')
  return mod.useDisplayStore.getState()
}

describe('displayStore hydration', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
  })

  it('restores previously saved values', async () => {
    const s = await freshStore(
      JSON.stringify({ uiScale: 1.5, terminalFontSize: 22 })
    )
    expect(s.uiScale).toBe(1.5)
    expect(s.terminalFontSize).toBe(22)
  })

  it('falls back to defaults when nothing is stored', async () => {
    const s = await freshStore(null)
    expect(s.uiScale).toBe(1)
    expect(s.terminalFontSize).toBe(14)
  })

  it('falls back to defaults on corrupt JSON instead of crashing the app', async () => {
    const s = await freshStore('{not json at all')
    expect(s.uiScale).toBe(1)
    expect(s.terminalFontSize).toBe(14)
  })

  it('clamps stored values that are out of range', async () => {
    const s = await freshStore(
      JSON.stringify({ uiScale: 42, terminalFontSize: 1 })
    )
    expect(s.uiScale).toBe(UI_SCALE_MAX)
    expect(s.terminalFontSize).toBe(TERM_FONT_MIN)
  })

  it('ignores fields of the wrong type', async () => {
    const s = await freshStore(
      JSON.stringify({ uiScale: 'huge', terminalFontSize: null })
    )
    expect(s.uiScale).toBe(1)
    expect(s.terminalFontSize).toBe(14)
  })

  it('uses the smaller default font size on a touch device', async () => {
    const original = window.matchMedia
    window.matchMedia = ((q: string) => ({
      matches: q.includes('coarse'),
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia

    const s = await freshStore(null)
    expect(s.terminalFontSize).toBe(10)

    window.matchMedia = original
  })
})

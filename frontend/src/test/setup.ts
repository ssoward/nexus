import '@testing-library/jest-dom'

// This runner's global `localStorage` is not a usable Storage object (Node
// starts with `--localstorage-file` but no valid path), and jsdom does not
// implement `matchMedia` at all. Both are relied on by app code that runs at
// module scope, so install minimal working versions for every test file.
// Individual tests can still override either one.

const memStore = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  writable: true,
  value: {
    getItem: (k: string) => memStore.get(k) ?? null,
    setItem: (k: string, v: string) => void memStore.set(k, String(v)),
    removeItem: (k: string) => void memStore.delete(k),
    clear: () => memStore.clear(),
    key: (i: number) => [...memStore.keys()][i] ?? null,
    get length() {
      return memStore.size
    },
  },
})

if (typeof window.matchMedia !== 'function') {
  // Default to a desktop, fine-pointer device.
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

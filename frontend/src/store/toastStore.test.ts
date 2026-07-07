import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useToastStore, toast } from './toastStore'

describe('toastStore', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] })
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('add appends a toast with a generated id and returns it', () => {
    const id = useToastStore.getState().add('hello', 'success')
    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0]).toMatchObject({ id, message: 'hello', type: 'success' })
  })

  it('defaults type to info', () => {
    useToastStore.getState().add('note')
    expect(useToastStore.getState().toasts[0].type).toBe('info')
  })

  it('auto-dismisses after the timeout', () => {
    useToastStore.getState().add('bye')
    expect(useToastStore.getState().toasts).toHaveLength(1)
    vi.advanceTimersByTime(4000)
    expect(useToastStore.getState().toasts).toHaveLength(0)
  })

  it('remove drops a specific toast', () => {
    const id1 = useToastStore.getState().add('a')
    const id2 = useToastStore.getState().add('b')
    useToastStore.getState().remove(id1)
    const ids = useToastStore.getState().toasts.map((t) => t.id)
    expect(ids).toEqual([id2])
  })

  it('toast.* helpers set the right type', () => {
    toast.error('boom')
    toast.warning('careful')
    const types = useToastStore.getState().toasts.map((t) => t.type)
    expect(types).toEqual(['error', 'warning'])
  })
})

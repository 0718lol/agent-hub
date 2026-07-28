import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { scheduleGenerationStatusCheck } from './generationStatus'

describe('generation status reconciliation', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    global.fetch = vi.fn()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('keeps polling while the durable job is active', async () => {
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ is_generating: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ is_generating: false }),
      })
    const timerRef = { current: null }
    const onState = vi.fn()

    scheduleGenerationStatusCheck('conv one', timerRef, onState, 10)
    await vi.advanceTimersByTimeAsync(10)

    expect(fetch).toHaveBeenCalledWith('/api/conversations/conv%20one/generation')
    expect(onState).toHaveBeenLastCalledWith(true)

    await vi.advanceTimersByTimeAsync(60000)
    expect(onState).toHaveBeenLastCalledWith(false)
    expect(timerRef.current).toBeNull()
  })

  it('does not unlock generation when the status request fails', async () => {
    fetch.mockRejectedValue(new Error('offline'))
    const timerRef = { current: null }
    const onState = vi.fn()

    scheduleGenerationStatusCheck('conv', timerRef, onState, 10)
    await vi.advanceTimersByTimeAsync(10)

    expect(onState).not.toHaveBeenCalled()
    expect(timerRef.current).not.toBeNull()
  })
})

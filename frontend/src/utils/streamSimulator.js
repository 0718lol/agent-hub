export function simulateStream(text, onChunk, onDone, speed = 35) {
  let index = 0
  const chars = text.split('')
  let timerId = null
  let cancelled = false

  const tick = () => {
    if (cancelled) return
    if (index >= chars.length) {
      onDone()
      return
    }

    const chunkSize = Math.random() > 0.8 ? 2 : 1
    const chunk = chars.slice(index, index + chunkSize).join('')
    index += chunkSize
    onChunk(chunk)

    const delay = speed + Math.random() * 30
    timerId = setTimeout(tick, delay)
  }

  tick()

  return () => {
    cancelled = true
    if (timerId) clearTimeout(timerId)
  }
}

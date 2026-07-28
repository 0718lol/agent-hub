export function scheduleGenerationStatusCheck(
  conversationId,
  timerRef,
  onState,
  delay = 60000,
) {
  if (timerRef.current) clearTimeout(timerRef.current)

  const check = async () => {
    try {
      const response = await fetch(
        `/api/conversations/${encodeURIComponent(conversationId)}/generation`,
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const status = await response.json()
      const active = Boolean(status.is_generating)
      onState(active)
      timerRef.current = active ? setTimeout(check, 60000) : null
    } catch (_error) {
      // Keep the UI locked while status is unknown; a short retry prevents
      // duplicate prompts during a temporary API or network interruption.
      timerRef.current = setTimeout(check, 15000)
    }
  }

  timerRef.current = setTimeout(check, delay)
}

import { useCallback, useEffect, useState } from 'react'

const INITIAL_STATE = {
  loading: true,
  service: 'offline',
  model: 'demo',
  buildServices: 'limited',
}

export function useReadiness() {
  const [readiness, setReadiness] = useState(INITIAL_STATE)

  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/readiness', { cache: 'no-store' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setReadiness({
        loading: false,
        service: data.readiness?.service || 'offline',
        model: data.readiness?.model || 'demo',
        buildServices: data.readiness?.build_services || 'limited',
      })
    } catch {
      setReadiness((current) => ({ ...current, loading: false, service: 'offline' }))
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = window.setInterval(refresh, 30000)
    window.addEventListener('agenthub:readiness-refresh', refresh)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('agenthub:readiness-refresh', refresh)
    }
  }, [refresh])

  return readiness
}

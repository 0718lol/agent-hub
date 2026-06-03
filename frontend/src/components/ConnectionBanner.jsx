import React, { useSyncExternalStore, useState, useEffect } from 'react'
import { WifiOff, RefreshCw, Loader2 } from 'lucide-react'
import { wsClient } from '../utils/websocket'

const STATUS_MAP = {
  connected: { bg: 'var(--green)', color: '#fff', icon: null, text: null },
  reconnecting: { bg: 'var(--orange)', color: '#fff', icon: Loader2, text: '连接已断开，正在重连...' },
  disconnected: { bg: 'var(--red)', color: '#fff', icon: WifiOff, text: '无法连接到服务器' },
}

export default function ConnectionBanner() {
  const status = useSyncExternalStore(
    wsClient.onStatusChange.bind(wsClient),
    () => wsClient.status,
  )

  const [visible, setVisible] = useState(false)
  const [fadeOut, setFadeOut] = useState(false)

  useEffect(() => {
    if (status === 'connected') {
      // Connected: fade out then hide
      setFadeOut(true)
      const timer = setTimeout(() => {
        setVisible(false)
        setFadeOut(false)
      }, 300)
      return () => clearTimeout(timer)
    } else {
      // Disconnected or reconnecting: show immediately
      setFadeOut(false)
      setVisible(true)
    }
  }, [status])

  if (!visible) return null

  const config = STATUS_MAP[status] || STATUS_MAP.disconnected
  const Icon = config.icon

  const handleRetry = () => {
    wsClient.reconnectAttempts = 0
    if (wsClient.currentConvId) {
      wsClient.connect(wsClient.currentConvId)
    }
  }

  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 'var(--z-toast, 100)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        padding: '6px 16px',
        background: config.bg,
        color: config.color,
        fontSize: 'var(--text-sm, 0.875rem)',
        fontWeight: 500,
        fontFamily: 'var(--font-ui)',
        opacity: fadeOut ? 0 : 1,
        transform: fadeOut ? 'translateY(-100%)' : 'translateY(0)',
        transition: 'opacity 0.3s ease, transform 0.3s ease',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
      }}
    >
      {Icon && (
        <Icon
          size={14}
          style={status === 'reconnecting' ? { animation: 'spin 1s linear infinite' } : undefined}
        />
      )}
      <span>{config.text}</span>
      {status === 'disconnected' && (
        <button
          onClick={handleRetry}
          aria-label="重新连接服务器"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            marginLeft: 8,
            padding: '2px 10px',
            background: 'rgba(255,255,255,0.2)',
            border: '1px solid rgba(255,255,255,0.3)',
            borderRadius: 'var(--radius-sm, 6px)',
            color: '#fff',
            fontSize: 'var(--text-xs, 0.75rem)',
            cursor: 'pointer',
            fontFamily: 'var(--font-ui)',
          }}
        >
          <RefreshCw size={12} />
          重新连接
        </button>
      )}
      {status === 'reconnecting' && wsClient.reconnectAttempts > 0 && (
        <span style={{ opacity: 0.8, fontSize: 'var(--text-xs, 0.75rem)' }}>
          (第 {wsClient.reconnectAttempts} 次重试)
        </span>
      )}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}

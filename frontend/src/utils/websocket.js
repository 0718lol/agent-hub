class WSClient {
  constructor() {
    this.ws = null
    this.handlers = new Set()
    this.reconnectTimer = null
    this.heartbeatTimer = null
    this.heartbeatInterval = 25000
    this.pendingMessages = []
    this.currentConvId = null
    this.reconnectAttempts = 0
    this.maxReconnectDelay = 30000 // Maximum 30 seconds
    this.baseReconnectDelay = 1000 // Start at 1 second
    this.maxReconnectAttempts = 5
    this.shouldReconnect = false
    // Connection status tracking
    this.status = 'disconnected' // 'connected' | 'reconnecting' | 'disconnected'
    this._statusListeners = new Set()
  }

  /** Register a callback for status changes. Returns unsubscribe function. */
  onStatusChange(callback) {
    this._statusListeners.add(callback)
    return () => this._statusListeners.delete(callback)
  }

  _setStatus(newStatus) {
    if (this.status === newStatus) return
    this.status = newStatus
    for (const fn of this._statusListeners) {
      try { fn(newStatus) } catch (e) { console.error('Status listener error:', e) }
    }
  }

  _stopHeartbeat() {
    clearInterval(this.heartbeatTimer)
    this.heartbeatTimer = null
  }

  _startHeartbeat(ws) {
    this._stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      if (this.ws === ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, this.heartbeatInterval)
  }

  connect(conversationId) {
    if (
      this.currentConvId === conversationId &&
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)
    ) {
      return
    }

    this.currentConvId = conversationId
    this.shouldReconnect = true
    clearTimeout(this.reconnectTimer)

    if (this.ws) {
      this._stopHeartbeat()
      const oldWs = this.ws
      oldWs.onclose = null // Prevents the old socket close from triggering a stale reconnection
      oldWs.close()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws/${conversationId}`

    const ws = new WebSocket(url)
    this.ws = ws
    this.status = 'reconnecting'

    ws.onopen = () => {
      if (this.ws !== ws) return // Safe guard against stale connections
      this.reconnectAttempts = 0
      this._setStatus('connected')
      this._startHeartbeat(ws)
      while (this.pendingMessages.length > 0) {
        const msg = this.pendingMessages.shift()
        ws.send(msg)
      }
    }

    ws.onmessage = (event) => {
      if (this.ws !== ws) return // Safe guard against stale connections
      try {
        const data = JSON.parse(event.data)
        this.handlers.forEach((fn) => fn(data))
      } catch (e) {
        console.error('WS parse error:', e)
      }
    }

    ws.onclose = (event) => {
      if (this.ws !== ws) return // Safe guard against stale connections
      this._stopHeartbeat()
      this.ws = null
      if (!this.shouldReconnect || this.currentConvId !== conversationId) return
      this.reconnectAttempts++
      if (event?.code === 4001 || this.reconnectAttempts > this.maxReconnectAttempts) {
        this.shouldReconnect = false
        this._setStatus('disconnected')
        return
      }
      this._setStatus('reconnecting')
      const delay = this._calculateReconnectDelay()
      this.reconnectTimer = setTimeout(() => this.connect(conversationId), delay)
    }

    ws.onerror = (err) => {
      if (this.ws !== ws) return // Safe guard against stale connections
      console.error('WS error:', err)
    }
  }

  /**
   * Calculate reconnect delay with exponential backoff + jitter.
   * delay = min(base * 2^attempts + random jitter, maxDelay)
   */
  _calculateReconnectDelay() {
    const exponentialDelay = this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts)
    const jitter = Math.random() * 1000 // Random jitter 0-1000ms
    return Math.min(exponentialDelay + jitter, this.maxReconnectDelay)
  }

  send(data) {
    const json = JSON.stringify(data)
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(json)
    } else {
      // Queue for sending once connected
      this.pendingMessages.push(json)
    }
  }

  /**
   * 强制发送：保证消息送达。如果 ws 未连接到 targetConvId，先连接再发。
   * 比 send() 安全，不会因 disconnect 丢失队列。
   */
  sendTo(targetConvId, data) {
    const json = JSON.stringify(data)
    if (this.ws && this.ws.readyState === WebSocket.OPEN && this.currentConvId === targetConvId) {
      this.ws.send(json)
      return
    }
    this.pendingMessages.push(json)
    this.connect(targetConvId)
  }

  onMessage(handler) {
    this.handlers.add(handler)
    return () => {
      this.handlers.delete(handler)
    }
  }

  disconnect() {
    this.shouldReconnect = false
    clearTimeout(this.reconnectTimer)
    this._stopHeartbeat()
    this.reconnectAttempts = 0
    this.pendingMessages = []
    this._setStatus('disconnected')
    if (this.ws) {
      const oldWs = this.ws
      oldWs.onclose = null
      oldWs.close()
      this.ws = null
    }
  }
}

export const wsClient = new WSClient()

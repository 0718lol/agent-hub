class WSClient {
  constructor() {
    this.ws = null
    this.connections = new Map() // convId -> { ws, reconnectAttempts, reconnectTimer, shouldReconnect }
    this.handlers = new Set()
    this.reconnectTimer = null
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

  _wsUrl(conversationId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws/${conversationId}`
  }

  _flushPendingFor(conversationId, ws) {
    const remaining = []
    for (const pending of this.pendingMessages) {
      if (!pending.conversationId || pending.conversationId === conversationId) {
        ws.send(pending.json)
      } else {
        remaining.push(pending)
      }
    }
    this.pendingMessages = remaining
  }

  _dispatchFrame(conversationId, ws, event) {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'ping') {
        ws.send(JSON.stringify({ type: 'pong' }))
        return
      }
      if (!data.conversation_id && conversationId) {
        data.conversation_id = conversationId
      }
      this.handlers.forEach((fn) => fn(data))
    } catch (e) {
      console.error('WS parse error:', e)
    }
  }

  /**
   * Multi-tab connection multiplexer: keeps WebSocket connections alive for all
   * open/generating tabs simultaneously so background conversations continue
   * streaming tokens, artifacts, and deployment updates without cross-talk.
   */
  syncConnections(conversationIds, activeConversationId) {
    const wanted = new Set((conversationIds || []).filter(Boolean))
    if (activeConversationId) {
      wanted.add(activeConversationId)
      this.currentConvId = activeConversationId
    }

    // Close pooled sockets that are no longer open or generating
    for (const [convId, entry] of this.connections.entries()) {
      if (!wanted.has(convId)) {
        entry.shouldReconnect = false
        clearTimeout(entry.reconnectTimer)
        if (entry.ws) {
          const oldWs = entry.ws
          oldWs.onclose = null
          oldWs.close()
        }
        this.connections.delete(convId)
      }
    }

    if (wanted.size === 0) {
      this.ws = null
      this._setStatus('disconnected')
      return
    }

    for (const convId of wanted) {
      this._openPooledConnection(convId)
    }

    const activeEntry = this.currentConvId ? this.connections.get(this.currentConvId) : null
    this.ws = activeEntry?.ws || null
    if (this.ws?.readyState === WebSocket.OPEN) {
      this._setStatus('connected')
    } else if (this.ws) {
      this._setStatus('reconnecting')
    }
  }

  _openPooledConnection(conversationId) {
    let entry = this.connections.get(conversationId)
    if (
      entry?.ws &&
      (entry.ws.readyState === WebSocket.CONNECTING || entry.ws.readyState === WebSocket.OPEN)
    ) {
      return entry.ws
    }

    if (!entry) {
      entry = {
        ws: null,
        reconnectAttempts: 0,
        reconnectTimer: null,
        shouldReconnect: true,
      }
      this.connections.set(conversationId, entry)
    }
    entry.shouldReconnect = true
    clearTimeout(entry.reconnectTimer)
    entry.reconnectTimer = null

    if (entry.ws) {
      const oldWs = entry.ws
      oldWs.onclose = null
      oldWs.close()
    }

    const ws = new WebSocket(this._wsUrl(conversationId))
    entry.ws = ws
    if (this.currentConvId === conversationId) {
      this.ws = ws
      this._setStatus('reconnecting')
    }

    ws.onopen = () => {
      if (entry.ws !== ws) return
      entry.reconnectAttempts = 0
      if (this.currentConvId === conversationId) {
        this.ws = ws
        this._setStatus('connected')
      }
      this._flushPendingFor(conversationId, ws)
    }

    ws.onmessage = (event) => {
      if (entry.ws !== ws) return
      this._dispatchFrame(conversationId, ws, event)
    }

    ws.onclose = (event) => {
      if (entry.ws !== ws) return
      entry.ws = null
      if (this.currentConvId === conversationId) {
        this.ws = null
      }
      if (!entry.shouldReconnect || !this.connections.has(conversationId)) return
      entry.reconnectAttempts++
      if (event?.code === 4001 || entry.reconnectAttempts > this.maxReconnectAttempts) {
        entry.shouldReconnect = false
        if (this.currentConvId === conversationId) {
          this._setStatus('disconnected')
        }
        return
      }
      if (this.currentConvId === conversationId) {
        this._setStatus('reconnecting')
      }
      const delay = this._calculateReconnectDelay(entry.reconnectAttempts)
      entry.reconnectTimer = setTimeout(() => this._openPooledConnection(conversationId), delay)
    }

    ws.onerror = (err) => {
      if (entry.ws !== ws) return
      console.error('WS error:', err)
    }

    return ws
  }

  connect(conversationId) {
    if (this.connections.size > 0) {
      const ids = new Set(this.connections.keys())
      ids.add(conversationId)
      this.syncConnections([...ids], conversationId)
      return
    }

    if (
      this.currentConvId === conversationId &&
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)
    ) {
      return
    }

    if (this.currentConvId !== conversationId) this.reconnectAttempts = 0
    this.currentConvId = conversationId
    this.shouldReconnect = true
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null

    if (this.ws) {
      const oldWs = this.ws
      oldWs.onclose = null // Prevents the old socket close from triggering a stale reconnection
      oldWs.close()
    }

    const ws = new WebSocket(this._wsUrl(conversationId))
    this.ws = ws
    this._setStatus('reconnecting')

    ws.onopen = () => {
      if (this.ws !== ws) return // Safe guard against stale connections
      this.reconnectAttempts = 0
      this._setStatus('connected')
      this._flushPendingFor(conversationId, ws)
    }

    ws.onmessage = (event) => {
      if (this.ws !== ws) return // Safe guard against stale connections
      this._dispatchFrame(conversationId, ws, event)
    }

    ws.onclose = (event) => {
      if (this.ws !== ws) return // Safe guard against stale connections
      this.ws = null
      if (!this.shouldReconnect || this.currentConvId !== conversationId) return
      this.reconnectAttempts++
      if (event?.code === 4001 || this.reconnectAttempts > this.maxReconnectAttempts) {
        this.shouldReconnect = false
        this._setStatus('disconnected')
        return
      }
      this._setStatus('reconnecting')
      const delay = this._calculateReconnectDelay(this.reconnectAttempts)
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
  _calculateReconnectDelay(attempts = this.reconnectAttempts) {
    const exponentialDelay = this.baseReconnectDelay * Math.pow(2, attempts)
    const jitter = Math.random() * 1000 // Random jitter 0-1000ms
    return Math.min(exponentialDelay + jitter, this.maxReconnectDelay)
  }

  send(data) {
    const json = JSON.stringify(data)
    const conversationId = data.conversation_id || this.currentConvId
    const pooled = conversationId ? this.connections.get(conversationId) : null
    if (pooled?.ws && pooled.ws.readyState === WebSocket.OPEN) {
      pooled.ws.send(json)
      return
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN && conversationId === this.currentConvId) {
      this.ws.send(json)
    } else {
      this.pendingMessages.push({ conversationId, json })
      if (this.connections.size > 0 && conversationId) {
        this._openPooledConnection(conversationId)
      } else if (conversationId && conversationId !== this.currentConvId) {
        this.connect(conversationId)
      }
    }
  }

  /**
   * 向指定会话发送消息。如果连接尚未建立，先排队并发起连接。
   */
  sendTo(targetConvId, data) {
    const json = JSON.stringify(data)
    const pooled = targetConvId ? this.connections.get(targetConvId) : null
    if (pooled?.ws && pooled.ws.readyState === WebSocket.OPEN) {
      pooled.ws.send(json)
      return
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN && this.currentConvId === targetConvId) {
      this.ws.send(json)
      return
    }
    this.pendingMessages.push({ conversationId: targetConvId, json })
    if (this.connections.size > 0 && targetConvId) {
      this._openPooledConnection(targetConvId)
    } else {
      this.connect(targetConvId)
    }
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
    this.reconnectTimer = null
    this.reconnectAttempts = 0
    this.pendingMessages = []
    for (const entry of this.connections.values()) {
      entry.shouldReconnect = false
      clearTimeout(entry.reconnectTimer)
      if (entry.ws) {
        const oldWs = entry.ws
        oldWs.onclose = null
        oldWs.close()
      }
    }
    this.connections.clear()
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

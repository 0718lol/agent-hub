class WSClient {
  constructor() {
    this.ws = null
    this.handlers = new Set()
    this.reconnectTimer = null
    this.pendingMessages = []
    this.currentConvId = null
    this.reconnectAttempts = 0
    this.maxReconnectDelay = 30000 // Maximum 30 seconds
    this.baseReconnectDelay = 1000 // Start at 1 second
  }

  connect(conversationId) {
    this.currentConvId = conversationId
    clearTimeout(this.reconnectTimer)

    if (this.ws) {
      const oldWs = this.ws
      oldWs.onclose = null // Prevents the old socket close from triggering a stale reconnection
      oldWs.close()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let url = `${protocol}//${window.location.host}/ws/${conversationId}`
    
    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      if (this.ws !== ws) return // Safe guard against stale connections
      const authToken = localStorage.getItem('agenthub_api_secret')
      if (authToken) {
        ws.send(JSON.stringify({ type: 'auth', token: authToken }))
      }
      this.reconnectAttempts = 0
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

    ws.onclose = () => {
      if (this.ws !== ws) return // Safe guard against stale connections
      const delay = this._calculateReconnectDelay()
      this.reconnectAttempts++
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

  onMessage(handler) {
    this.handlers.add(handler)
    return () => {
      this.handlers.delete(handler)
    }
  }

  disconnect() {
    clearTimeout(this.reconnectTimer)
    this.reconnectAttempts = 0
    this.pendingMessages = []
    if (this.ws) {
      const oldWs = this.ws
      oldWs.onclose = null
      oldWs.close()
      this.ws = null
    }
  }
}

export const wsClient = new WSClient()

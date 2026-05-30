class WSClient {
  constructor() {
    this.ws = null
    this.handlers = new Set()
    this.reconnectTimer = null
    this.pendingMessages = []
    this.currentConvId = null
    this.intentionalClose = false
    this.reconnectAttempts = 0
    this.maxReconnectDelay = 30000 // Maximum 30 seconds
    this.baseReconnectDelay = 1000 // Start at 1 second
  }

  connect(conversationId) {
    this.currentConvId = conversationId
    this.intentionalClose = false
    clearTimeout(this.reconnectTimer)

    if (this.ws) {
      this.intentionalClose = true
      this.ws.close()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let url = `${protocol}//${window.location.host}/ws/${conversationId}`
    
    // 自动追加可能存在的 API 鉴权 Token
    const token = localStorage.getItem('agenthub_api_secret')
    if (token) {
      url += `?token=${encodeURIComponent(token)}`
    }
    
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      // Reset reconnect attempts on successful connection
      this.reconnectAttempts = 0
      // Flush any messages queued while connecting
      while (this.pendingMessages.length > 0) {
        const msg = this.pendingMessages.shift()
        this.ws.send(msg)
      }
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.handlers.forEach((fn) => fn(data))
      } catch (e) {
        console.error('WS parse error:', e)
      }
    }

    this.ws.onclose = () => {
      if (!this.intentionalClose && this.currentConvId === conversationId) {
        const delay = this._calculateReconnectDelay()
        this.reconnectAttempts++
        this.reconnectTimer = setTimeout(() => this.connect(conversationId), delay)
      }
    }

    this.ws.onerror = (err) => {
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
    this.intentionalClose = true
    this.reconnectAttempts = 0
    this.pendingMessages = []
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}

export const wsClient = new WSClient()

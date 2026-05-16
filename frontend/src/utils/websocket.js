class WSClient {
  constructor() {
    this.ws = null
    this.handlers = []
    this.reconnectTimer = null
    this.pendingMessages = []
    this.currentConvId = null
    this.intentionalClose = false
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
    const url = `${protocol}//${window.location.host}/ws/${conversationId}`
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
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
        this.reconnectTimer = setTimeout(() => this.connect(conversationId), 3000)
      }
    }

    this.ws.onerror = (err) => {
      console.error('WS error:', err)
    }
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
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  disconnect() {
    clearTimeout(this.reconnectTimer)
    this.intentionalClose = true
    this.pendingMessages = []
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}

export const wsClient = new WSClient()

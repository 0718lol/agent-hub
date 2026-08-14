import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"

// Manual WebSocket mock
class MockWebSocket {
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = MockWebSocket.CONNECTING
    this.onopen = null
    this.onclose = null
    this.onmessage = null
    this.onerror = null
    this.sentMessages = []
    this._listeners = {}
    MockWebSocket.instances.push(this)
    this._openTimeout = setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      if (this.onopen) this.onopen(new Event("open"))
      const openListeners = this._listeners["open"] || []
      openListeners.forEach((fn) => fn(new Event("open")))
    }, 0)
  }

  send(data) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error("WebSocket is not open")
    }
    this.sentMessages.push(data)
  }

  close(code = 1000) {
    clearTimeout(this._openTimeout)
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) this.onclose({ code })
  }

  addEventListener(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = []
    this._listeners[event].push(fn)
  }

  removeEventListener(event, fn) {
    if (!this._listeners[event]) return
    this._listeners[event] = this._listeners[event].filter((f) => f !== fn)
  }
}

MockWebSocket.CONNECTING = 0
MockWebSocket.OPEN = 1
MockWebSocket.CLOSING = 2
MockWebSocket.CLOSED = 3

// Stub only WebSocket and localStorage, NOT window (to avoid clobbering jsdom)
vi.stubGlobal("WebSocket", MockWebSocket)

const storage = {}
vi.stubGlobal("localStorage", {
  getItem: vi.fn((key) => storage[key] || null),
  setItem: vi.fn((key, val) => { storage[key] = val }),
  removeItem: vi.fn((key) => { delete storage[key] }),
  clear: vi.fn(() => { for (const k in storage) delete storage[k] }),
})

// Patch window.location for the websocket URL construction
Object.defineProperty(window, "location", {
  value: { protocol: "http:", host: "localhost:8000" },
  writable: true,
  configurable: true,
})

// Import the module under test
import { wsClient } from "./websocket.js"

describe("WSClient (websocket.js)", () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    wsClient.disconnect()
    wsClient.handlers.clear()
    wsClient.reconnectAttempts = 0
    wsClient.pendingMessages = []
    wsClient.currentConvId = null
    wsClient.reconnectTimer = null
    wsClient.status = "disconnected"

    // Reset localStorage mock
    localStorage.getItem.mockReset()
    localStorage.getItem.mockReturnValue(null)
    for (const k in storage) delete storage[k]
  })

  afterEach(() => {
    wsClient.disconnect()
  })

  it("connect opens a WebSocket to the correct URL", async () => {
    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1))
    expect(MockWebSocket.instances[0].url).toBe("ws://localhost:8000/ws/conv_test_001")
  })

  it("connect never exposes a legacy token in the URL", async () => {
    localStorage.getItem.mockImplementation((key) => {
      if (key === "agenthub_api_secret") return "test-token-123"
      return null
    })

    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1))
    const ws = MockWebSocket.instances[0]
    expect(ws.url).toBe("ws://localhost:8000/ws/conv_test_001")
    expect(ws.url).not.toContain("token=")
  })

  it("connect does not send auth when no token stored", async () => {
    localStorage.getItem.mockReturnValue(null)

    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1))
    const ws = MockWebSocket.instances[0]
    await new Promise((r) => setTimeout(r, 50))
    expect(ws.sentMessages.length).toBe(0)
  })

  it("send queues messages when not connected", () => {
    wsClient.send({ type: "message", text: "hello" })

    expect(wsClient.pendingMessages.length).toBe(1)
    expect(JSON.parse(wsClient.pendingMessages[0].json).text).toBe("hello")
  })

  it("send transmits JSON when connected", async () => {
    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const ws = MockWebSocket.instances[0]
    ws.sentMessages = []

    wsClient.send({ type: "message", text: "hello world" })

    expect(ws.sentMessages.length).toBe(1)
    const sent = JSON.parse(ws.sentMessages[0])
    expect(sent.type).toBe("message")
    expect(sent.text).toBe("hello world")
  })

  it("flushes pending messages after connect", async () => {
    wsClient.send({ type: "message", text: "queued" })

    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const ws = MockWebSocket.instances[0]
    const texts = ws.sentMessages.map((m) => JSON.parse(m).text).filter(Boolean)
    expect(texts).toContain("queued")
  })

  it("does not flush a queued message into another conversation", async () => {
    wsClient.currentConvId = "conv_a"
    wsClient.send({ type: "message", conversation_id: "conv_a", text: "for-a" })
    wsClient.connect("conv_b")
    await vi.waitFor(() => expect(MockWebSocket.instances.at(-1).readyState).toBe(MockWebSocket.OPEN))

    const socketB = MockWebSocket.instances.at(-1)
    expect(socketB.sentMessages).toHaveLength(0)
    expect(wsClient.pendingMessages).toHaveLength(1)
    expect(wsClient.pendingMessages[0].conversationId).toBe("conv_a")
  })

  it("onMessage registers handler and receives parsed data", async () => {
    const received = []
    const unsub = wsClient.onMessage((data) => received.push(data))

    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const ws = MockWebSocket.instances[0]
    ws.onmessage({ data: JSON.stringify({ type: "message", content: { text: "hi" } }) })

    expect(received.length).toBe(1)
    expect(received[0].type).toBe("message")
    expect(received[0].content.text).toBe("hi")

    unsub()
  })

  it("onMessage unsubscribe stops receiving messages", async () => {
    const received = []
    const unsub = wsClient.onMessage((data) => received.push(data))

    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const ws = MockWebSocket.instances[0]
    ws.onmessage({ data: JSON.stringify({ type: "message", content: { text: "first" } }) })
    expect(received.length).toBe(1)

    unsub()
    ws.onmessage({ data: JSON.stringify({ type: "message", content: { text: "second" } }) })
    expect(received.length).toBe(1)
  })

  it("onMessage handles multiple handlers", async () => {
    const received1 = []
    const received2 = []
    wsClient.onMessage((data) => received1.push(data))
    wsClient.onMessage((data) => received2.push(data))

    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const ws = MockWebSocket.instances[0]
    ws.onmessage({ data: JSON.stringify({ type: "test", value: 42 }) })

    expect(received1.length).toBe(1)
    expect(received2.length).toBe(1)
    expect(received1[0].value).toBe(42)
  })

  it("disconnect closes socket and resets state", async () => {
    wsClient.connect("conv_test_001")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const ws = MockWebSocket.instances[0]
    expect(ws.readyState).toBe(MockWebSocket.OPEN)

    wsClient.disconnect()

    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
    expect(wsClient.ws).toBeNull()
    expect(wsClient.pendingMessages.length).toBe(0)
  })

  it("connect replaces previous connection safely", async () => {
    wsClient.connect("conv_1")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const firstWs = MockWebSocket.instances[0]
    wsClient.connect("conv_2")
    await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(2))
    await vi.waitFor(() => expect(MockWebSocket.instances[1].readyState).toBe(MockWebSocket.OPEN))

    const secondWs = MockWebSocket.instances[1]

    expect(firstWs.readyState).toBe(MockWebSocket.CLOSED)
    expect(secondWs.readyState).toBe(MockWebSocket.OPEN)
    expect(secondWs.url).toBe("ws://localhost:8000/ws/conv_2")
    expect(wsClient.currentConvId).toBe("conv_2")
  })

  it("connect reuses an open socket for the same conversation", async () => {
    wsClient.connect("conv_same")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    wsClient.connect("conv_same")

    expect(MockWebSocket.instances.length).toBe(1)
    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN)
  })

  it("does not reconnect after an authentication failure", async () => {
    wsClient.connect("conv_auth")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    MockWebSocket.instances[0].close(4001)

    expect(wsClient.status).toBe("disconnected")
    expect(wsClient.shouldReconnect).toBe(false)
    expect(wsClient.reconnectTimer).toBeNull()
  })

  it("sendTo sends to correct conversation", async () => {
    wsClient.connect("conv_a")
    await vi.waitFor(() => expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.OPEN))

    const ws = MockWebSocket.instances[0]
    ws.sentMessages = []

    wsClient.sendTo("conv_a", { type: "ping" })

    expect(ws.sentMessages.length).toBe(1)
    expect(JSON.parse(ws.sentMessages[0]).type).toBe("ping")
  })
})

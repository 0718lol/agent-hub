import React from 'react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, act } from '@testing-library/react'
import ChatPanel from './ChatPanel'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import { useTabStore } from '../../stores/tabStore'
import { wsClient } from '../../utils/websocket'

class StubWebSocket {
  static byUrl = new Map()

  constructor(url) {
    this.url = url
    this.readyState = 1
    this.sent = []
    StubWebSocket.byUrl.set(url, this)
    setTimeout(() => this.onopen?.({ type: 'open' }), 0)
  }

  send(raw) {
    this.sent.push(JSON.parse(raw))
  }

  close() {
    this.readyState = 3
  }
}
StubWebSocket.CONNECTING = 0
StubWebSocket.OPEN = 1
StubWebSocket.CLOSING = 2
StubWebSocket.CLOSED = 3

describe('ChatPanel multi-session concurrent isolation', () => {
  beforeEach(() => {
    StubWebSocket.byUrl.clear()
    vi.stubGlobal('WebSocket', StubWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, json: async () => [] }))
    )
    wsClient.disconnect()
    useChatStore.getState().setOwner('tenant-iso')
    useCanvasStore.getState().setOwner('tenant-iso')
    useTabStore.setState({
      _ownerId: 'tenant-iso',
      openTabs: [
        { id: 'tab_conv_pm', convId: 'conv_pm', title: 'PM 小助手', agentId: 'agent_pm' },
        { id: 'tab_conv_frontend', convId: 'conv_frontend', title: '前端工程师', agentId: 'agent_frontend' },
      ],
      activeTabId: 'tab_conv_frontend',
      lastActive: new Map([
        ['tab_conv_pm', 1],
        ['tab_conv_frontend', 2],
      ]),
      _synced: true,
    })
  })

  afterEach(() => {
    wsClient.disconnect()
    vi.unstubAllGlobals()
  })

  it('routes background tab WebSocket code, preview, deploy, and messages without polluting active tab', async () => {
    const { unmount } = render(<ChatPanel onToggleSidebar={() => {}} readiness={{ workbench: false }} />)

    await vi.waitFor(() => {
      expect(StubWebSocket.byUrl.size).toBe(2)
    })

    const pmSocket = [...StubWebSocket.byUrl.entries()].find(([url]) => url.endsWith('/ws/conv_pm'))?.[1]
    expect(pmSocket).toBeDefined()

    // Emit streaming code + preview + deploy + message on background tab conv_pm
    act(() => {
      pmSocket.onmessage({
        data: JSON.stringify({
          type: 'code',
          conversation_id: 'conv_pm',
          language: 'html',
          code: '<h1>PM Secret Prototype</h1>',
        }),
      })
      pmSocket.onmessage({
        data: JSON.stringify({
          type: 'deploy_status',
          conversation_id: 'conv_pm',
          status: 'running',
          log: 'Building PM container...',
        }),
      })
      pmSocket.onmessage({
        data: JSON.stringify({
          type: 'message',
          conversation_id: 'conv_pm',
          sender: 'agent_pm',
          content: { text: 'PM 原型已就绪' },
          stream: false,
        }),
      })
    })

    // Active tab is still conv_frontend -> top-level canvasStore must remain clean!
    expect(useCanvasStore.getState().activeConversationId).toBe('conv_frontend')
    expect(useCanvasStore.getState().previewHtml).toBeNull()
    expect(useCanvasStore.getState().generatedCode).toBeNull()
    expect(useCanvasStore.getState().deployStatus).toBe('idle')

    // Meanwhile conv_pm's chat history received the message & unread badge, and its canvas bucket has the artifact
    const pmConv = useChatStore.getState().conversations.find((c) => c.id === 'conv_pm')
    expect(pmConv.messages.at(-1)?.content?.text).toBe('PM 原型已就绪')
    expect(pmConv.unread).toBe(true)

    // Switch active tab back to conv_pm -> PM's preview, code, and running deploy state appear immediately!
    act(() => {
      useTabStore.getState().setActiveTab('tab_conv_pm')
    })

    await vi.waitFor(() => {
      expect(useCanvasStore.getState().activeConversationId).toBe('conv_pm')
    })
    expect(useCanvasStore.getState().previewHtml).toBe('<h1>PM Secret Prototype</h1>')
    expect(useCanvasStore.getState().deployStatus).toBe('running')
    expect(useCanvasStore.getState().deployLogs).toEqual(['Building PM container...'])

    unmount()
  })
})

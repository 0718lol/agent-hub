import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'

describe('chatStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useChatStore.setState({
      conversations: useChatStore.getInitialState().conversations,
      activeConversationId: 'conv_pm',
      typingAgents: {},
      thinkingAgents: {},
      generatingConvs: new Set(),
      allRead: {},
      pinnedMessages: {},
    })
  })

  it('should have default conversations', () => {
    const state = useChatStore.getState()
    expect(state.conversations.length).toBeGreaterThan(0)
  })

  it('should set active conversation', () => {
    const { setActiveConversation } = useChatStore.getState()
    setActiveConversation('conv_frontend')
    expect(useChatStore.getState().activeConversationId).toBe('conv_frontend')
  })

  it('should add a message with unique ID', () => {
    const { addMessage } = useChatStore.getState()
    addMessage('conv_pm', { sender: 'user', content: { text: 'Hello' } })
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_pm')
    expect(conv.messages.length).toBe(1)
    // Message ID should be a UUID or unique string, not Date.now()+Math.random()
    const msgId = conv.messages[0].id
    expect(typeof msgId).toBe('string')
    expect(msgId.length).toBeGreaterThan(5)
  })

  it('should prevent duplicate messages by id', () => {
    const { addMessage } = useChatStore.getState()
    const msg = { id: 'test-msg-001', sender: 'user', content: { text: 'Hello' } }
    addMessage('conv_pm', msg)
    addMessage('conv_pm', msg) // duplicate
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_pm')
    expect(conv.messages.length).toBe(1)
  })

  it('should set typing state', () => {
    const { setTyping } = useChatStore.getState()
    setTyping('conv_pm', 'agent_pm', true)
    const state = useChatStore.getState()
    expect(state.typingAgents['conv_pm'].has('agent_pm')).toBe(true)
  })

  it('should set thinking state', () => {
    const { setThinking } = useChatStore.getState()
    setThinking('conv_pm', 'agent_pm', 'Analyzing requirements...')
    const state = useChatStore.getState()
    expect(state.thinkingAgents['conv_pm']['agent_pm']).toBe('Analyzing requirements...')
  })

  it('should clear thinking state when text is empty', () => {
    const { setThinking } = useChatStore.getState()
    setThinking('conv_pm', 'agent_pm', 'Thinking...')
    setThinking('conv_pm', 'agent_pm', '')
    const state = useChatStore.getState()
    expect(state.thinkingAgents['conv_pm']['agent_pm']).toBeUndefined()
  })

  it('should set generating state', () => {
    const { setGenerating } = useChatStore.getState()
    setGenerating('conv_pm', true)
    expect(useChatStore.getState().generatingConvs.has('conv_pm')).toBe(true)
    setGenerating('conv_pm', false)
    expect(useChatStore.getState().generatingConvs.has('conv_pm')).toBe(false)
  })

  it('should mark conversation as read', () => {
    const { markRead } = useChatStore.getState()
    markRead('conv_pm')
    expect(useChatStore.getState().allRead['conv_pm']).toBe(true)
  })

  it('should clear messages for a conversation', () => {
    const { addMessage, clearMessages } = useChatStore.getState()
    addMessage('conv_pm', { sender: 'user', content: { text: 'Hello' } })
    clearMessages('conv_pm')
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_pm')
    expect(conv.messages.length).toBe(0)
  })

  it('should add and remove conversations', () => {
    const { addConversation, removeConversation } = useChatStore.getState()
    addConversation({ id: 'conv_test', type: 'single', name: 'Test', messages: [] })
    expect(useChatStore.getState().conversations.find(c => c.id === 'conv_test')).toBeDefined()
    removeConversation('conv_test')
    expect(useChatStore.getState().conversations.find(c => c.id === 'conv_test')).toBeUndefined()
  })

  it('should toggle pin on conversation', () => {
    const { togglePin } = useChatStore.getState()
    togglePin('conv_pm')
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_pm')
    expect(conv.pinned).toBe(true)
    togglePin('conv_pm')
    expect(conv.pinned).toBe(false)
  })
})

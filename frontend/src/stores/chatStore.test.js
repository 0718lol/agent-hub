import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useChatStore } from './chatStore'

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.setState({
      conversations: [],
      activeConversationId: null,
      typingAgents: {},
      thinkingAgents: {},
      generatingConvs: new Set(),
      allRead: {},
      pinnedMessages: {},
    })
  })

  // ---------- addConversation ----------

  it('should add a new conversation', () => {
    useChatStore.getState().addConversation({ id: 'conv_test_001', type: 'single', name: '测试会话', avatar: '🤖' })
    const convs = useChatStore.getState().conversations
    expect(convs.some(c => c.id === 'conv_test_001')).toBe(true)
    expect(convs.find(c => c.id === 'conv_test_001').name).toBe('测试会话')
  })

  it('should set default fields on added conversation', () => {
    useChatStore.getState().addConversation({ id: 'conv_new', name: 'New' })
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_new')
    expect(conv.unread).toBe(false)
    expect(conv.pinned).toBe(false)
    expect(conv.updatedAt).toBeDefined()
  })

  it('should ignore duplicate conversation id', () => {
    useChatStore.getState().addConversation({ id: 'conv_dup', name: 'First' })
    useChatStore.getState().addConversation({ id: 'conv_dup', name: 'Second' })
    const matches = useChatStore.getState().conversations.filter(c => c.id === 'conv_dup')
    expect(matches.length).toBe(1)
    expect(matches[0].name).toBe('First')
  })

  // ---------- removeConversation ----------

  it('should remove conversation from list', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_a', name: 'A' })
    store.addConversation({ id: 'conv_b', name: 'B' })
    store.removeConversation('conv_a')
    const convs = useChatStore.getState().conversations
    expect(convs.some(c => c.id === 'conv_a')).toBe(false)
    expect(convs.some(c => c.id === 'conv_b')).toBe(true)
  })

  it('should switch activeId when deleting the active conversation', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_a', name: 'A' })
    store.addConversation({ id: 'conv_b', name: 'B' })
    store.setActiveConversation('conv_a')
    store.removeConversation('conv_a')
    expect(useChatStore.getState().activeConversationId).not.toBe('conv_a')
    expect(useChatStore.getState().activeConversationId).toBe('conv_b')
  })

  it('should fall back to conv_pm when no conversations remain', () => {
    useChatStore.getState().addConversation({ id: 'conv_solo', name: 'Solo' })
    useChatStore.getState().setActiveConversation('conv_solo')
    useChatStore.getState().removeConversation('conv_solo')
    expect(useChatStore.getState().activeConversationId).toBe('conv_pm')
  })

  it('should keep activeId when deleting non-active conversation', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_a', name: 'A' })
    store.addConversation({ id: 'conv_b', name: 'B' })
    store.setActiveConversation('conv_a')
    store.removeConversation('conv_b')
    expect(useChatStore.getState().activeConversationId).toBe('conv_a')
  })

  // ---------- updateConversation ----------

  it('should update conversation fields', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: '旧名字', avatar: '🤖' })
    store.updateConversation('conv_001', { name: '新名字' })
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_001')
    expect(conv.name).toBe('新名字')
    expect(conv.avatar).toBe('🤖')
  })

  // ---------- setActiveConversation ----------

  it('should set active conversation id', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A' })
    store.setActiveConversation('conv_001')
    expect(useChatStore.getState().activeConversationId).toBe('conv_001')
  })

  // ---------- getActiveConversation ----------

  it('should return the active conversation object', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A' })
    store.setActiveConversation('conv_001')
    const active = store.getActiveConversation()
    expect(active.id).toBe('conv_001')
    expect(active.name).toBe('A')
  })

  // ---------- addMessage ----------

  it('should add message to conversation', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A', messages: [] })
    store.addMessage('conv_001', { sender: 'user', content: { text: 'hello' } })
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_001')
    expect(conv.messages.length).toBe(1)
    expect(conv.messages[0].sender).toBe('user')
    expect(conv.messages[0].content.text).toBe('hello')
  })

  it('should generate unique message id when not provided', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A', messages: [] })
    store.addMessage('conv_001', { sender: 'user', content: { text: 'a' } })
    store.addMessage('conv_001', { sender: 'user', content: { text: 'b' } })
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_001')
    expect(conv.messages.length).toBe(2)
    expect(conv.messages[0].id).not.toBe(conv.messages[1].id)
  })

  it('should deduplicate messages by id', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A', messages: [] })
    store.addMessage('conv_001', { id: 'msg_dup', sender: 'user', content: { text: 'first' } })
    store.addMessage('conv_001', { id: 'msg_dup', sender: 'user', content: { text: 'second' } })
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_001')
    expect(conv.messages.length).toBe(1)
    expect(conv.messages[0].content.text).toBe('first')
  })

  it('should add timestamp to message if not provided', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A', messages: [] })
    store.addMessage('conv_001', { sender: 'user', content: { text: 'hi' } })
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_001')
    expect(conv.messages[0].timestamp).toBeDefined()
  })

  // ---------- clearMessages ----------

  it('should clear all messages in a conversation', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A', messages: [] })
    store.addMessage('conv_001', { id: 'msg_001', sender: 'user', content: { text: 'hi' } })
    store.clearMessages('conv_001')
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_001')
    expect(conv.messages.length).toBe(0)
  })

  // ---------- togglePin ----------

  it('should toggle pinned state on conversation', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A' })
    expect(useChatStore.getState().conversations.find(c => c.id === 'conv_001').pinned).toBe(false)
    store.togglePin('conv_001')
    expect(useChatStore.getState().conversations.find(c => c.id === 'conv_001').pinned).toBe(true)
    store.togglePin('conv_001')
    expect(useChatStore.getState().conversations.find(c => c.id === 'conv_001').pinned).toBe(false)
  })

  // ---------- archiveConversation ----------

  it('should archive a conversation', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A' })
    store.archiveConversation('conv_001')
    const conv = useChatStore.getState().conversations.find(c => c.id === 'conv_001')
    expect(conv.archived).toBe(true)
  })

  // ---------- setTyping ----------

  it('should track typing agents per conversation', () => {
    const store = useChatStore.getState()
    store.setTyping('conv_001', 'agent_pm', true)
    expect(useChatStore.getState().typingAgents['conv_001'].has('agent_pm')).toBe(true)
    store.setTyping('conv_001', 'agent_pm', false)
    expect(useChatStore.getState().typingAgents['conv_001'].has('agent_pm')).toBe(false)
  })

  // ---------- setThinking ----------

  it('should set thinking text for an agent', () => {
    const store = useChatStore.getState()
    store.setThinking('conv_001', 'agent_pm', '正在分析需求...')
    expect(useChatStore.getState().thinkingAgents['conv_001']['agent_pm']).toBe('正在分析需求...')
  })

  it('should clear thinking state when text is empty', () => {
    const store = useChatStore.getState()
    store.setThinking('conv_001', 'agent_pm', 'Thinking...')
    store.setThinking('conv_001', 'agent_pm', '')
    expect(useChatStore.getState().thinkingAgents['conv_001']['agent_pm']).toBeUndefined()
  })

  // ---------- setGenerating ----------

  it('should track generating conversations', () => {
    const store = useChatStore.getState()
    store.setGenerating('conv_001', true)
    expect(useChatStore.getState().generatingConvs.has('conv_001')).toBe(true)
    store.setGenerating('conv_001', false)
    expect(useChatStore.getState().generatingConvs.has('conv_001')).toBe(false)
  })

  // ---------- markRead / markSent ----------

  it('should mark conversation as read', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_001', name: 'A' })
    store.markRead('conv_001')
    expect(useChatStore.getState().allRead['conv_001']).toBe(true)
    expect(useChatStore.getState().conversations.find(c => c.id === 'conv_001').unread).toBe(false)
  })

  it('should mark conversation as sent', () => {
    const store = useChatStore.getState()
    store.markSent('conv_001')
    expect(useChatStore.getState().allRead['conv_001']).toBe(false)
  })

  // ---------- togglePinMessage ----------

  it('should toggle pinned message in a conversation', () => {
    const store = useChatStore.getState()
    store.togglePinMessage('conv_001', 'msg_001')
    expect(useChatStore.getState().pinnedMessages['conv_001']).toContain('msg_001')
    store.togglePinMessage('conv_001', 'msg_001')
    expect(useChatStore.getState().pinnedMessages['conv_001']).not.toContain('msg_001')
  })

  // ---------- reorderConversations ----------

  it('should reorder conversations', () => {
    const store = useChatStore.getState()
    store.addConversation({ id: 'conv_1', name: 'First' })
    store.addConversation({ id: 'conv_2', name: 'Second' })
    store.addConversation({ id: 'conv_3', name: 'Third' })
    store.reorderConversations(0, 2)
    const convs = useChatStore.getState().conversations
    expect(convs[2].id).toBe('conv_1')
  })
})


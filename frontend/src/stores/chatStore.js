import { create } from 'zustand'

/** Map backend conversation to frontend shape */
function mapConversation(c) {
  return {
    id: c.id,
    type: c.type,
    name: c.name,
    avatar: c.avatar || null,
    agentId: c.agent_id || null,
    agents: c.agents ? (typeof c.agents === 'string' ? JSON.parse(c.agents) : c.agents) : undefined,
    role: c.preview || '',
    preview: c.preview || '',
    messages: [],
    pinned: false,
    unread: false,
    updatedAt: c.created_at ? new Date(c.created_at).getTime() : Date.now(),
  }
}

/** Fallback conversations when backend is unavailable */
const FALLBACK_CONVERSATIONS = [
  { id: 'conv_pm', type: 'single', agentId: 'agent_pm', name: 'PM 小助手', avatar: null, role: '需求分析与任务拆解', messages: [], pinned: false, unread: false, updatedAt: Date.now() },
  { id: 'conv_frontend', type: 'single', agentId: 'agent_frontend', name: '前端工程师', avatar: null, role: 'React 组件与样式开发', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 1000 },
  { id: 'conv_backend', type: 'single', agentId: 'agent_backend', name: '后端工程师', avatar: null, role: 'API 接口与数据模型', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 2000 },
  { id: 'conv_tester', type: 'single', agentId: 'agent_tester', name: '测试工程师', avatar: null, role: '测试用例与 Bug 分析', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 3000 },
  { id: 'conv_devops', type: 'single', agentId: 'agent_devops', name: '运维工程师', avatar: null, role: 'Docker 部署与 CI/CD', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 4000 },
  { id: 'conv_designer', type: 'single', agentId: 'agent_designer', name: '设计顾问', avatar: null, role: 'UI/UX 设计建议', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 5000 },
  { id: 'conv_agent_builder', type: 'single', agentId: 'agent_builder', name: 'Agent 工坊', avatar: null, role: '对话式创建自定义 Agent', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 6000 },
  { id: 'conv_group_demo', type: 'group', name: 'Demo 项目群', avatar: null, agents: ['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer'], messages: [], pinned: false, unread: false, updatedAt: Date.now() - 7000 },
]

export const useChatStore = create((set, get) => ({
  conversations: FALLBACK_CONVERSATIONS,
  activeConversationId: 'conv_pm',
  typingAgents: {},
  thinkingAgents: {},
  generatingConvs: new Set(),
  allRead: {},
  pinnedMessages: {},

  setActiveConversation: (id) => set({ activeConversationId: id }),

  togglePin: (conversationId) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId ? { ...c, pinned: !c.pinned } : c
      ),
    })),

  archiveConversation: (conversationId) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId ? { ...c, archived: true } : c
      ),
    })),

  reorderConversations: (fromIndex, toIndex) =>
    set((state) => {
      const list = [...state.conversations]
      const [moved] = list.splice(fromIndex, 1)
      list.splice(toIndex, 0, moved)
      return { conversations: list }
    }),

  togglePinMessage: (conversationId, messageId) =>
    set((state) => {
      const current = state.pinnedMessages[conversationId] || []
      const next = current.includes(messageId)
        ? current.filter((id) => id !== messageId)
        : [...current, messageId]
      return { pinnedMessages: { ...state.pinnedMessages, [conversationId]: next } }
    }),

  setTyping: (conversationId, agentId, isTyping) =>
    set((state) => {
      const current = new Set(state.typingAgents[conversationId] || [])
      if (isTyping) current.add(agentId)
      else current.delete(agentId)
      return { typingAgents: { ...state.typingAgents, [conversationId]: current } }
    }),

  setThinking: (conversationId, agentId, text) =>
    set((state) => {
      const convThinking = { ...(state.thinkingAgents[conversationId] || {}) }
      if (text) { convThinking[agentId] = text }
      else { delete convThinking[agentId] }
      return { thinkingAgents: { ...state.thinkingAgents, [conversationId]: convThinking } }
    }),

  setGenerating: (conversationId, isGenerating) =>
    set((state) => {
      const next = new Set(state.generatingConvs)
      if (isGenerating) next.add(conversationId)
      else next.delete(conversationId)
      return { generatingConvs: next }
    }),

  markRead: (conversationId) =>
    set((state) => ({
      allRead: { ...state.allRead, [conversationId]: true },
      conversations: state.conversations.map((c) =>
        c.id === conversationId ? { ...c, unread: false } : c
      ),
    })),

  markSent: (conversationId) =>
    set((state) => ({
      allRead: { ...state.allRead, [conversationId]: false },
    })),

  loadMessages: async (conversationId) => {
    try {
      const resp = await fetch(`/api/conversations/${conversationId}/messages`)
      const messages = await resp.json()
      set((state) => ({
        conversations: state.conversations.map((conv) =>
          conv.id === conversationId
            ? { ...conv, messages, updatedAt: Date.now() }
            : conv
        ),
      }))
    } catch (e) {
      console.error('Failed to load messages:', e)
    }
  },

  addMessage: (conversationId, message) =>
    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv
        // 如果提供了 id，检查是否已存在（防止重复）
        if (message.id && conv.messages.some((m) => m.id === message.id)) return conv
        const msgId = message.id || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2))
        return {
          ...conv,
          messages: [...conv.messages, { ...message, id: msgId, timestamp: message.timestamp || new Date().toISOString() }],
          updatedAt: Date.now(),
          unread: message.sender !== 'user' && conversationId !== state.activeConversationId,
        }
      }),
    })),

  clearMessages: (conversationId) =>
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId ? { ...conv, messages: [], preview: '' } : conv
      ),
      typingAgents: { ...state.typingAgents, [conversationId]: new Set() },
      thinkingAgents: { ...state.thinkingAgents, [conversationId]: {} },
    })),

  updateLastAgentMessage: (conversationId, senderId, text, streaming) =>
    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv
        const messages = [...conv.messages]
        let targetIdx = -1
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].sender === senderId && messages[i].streaming) {
            targetIdx = i
            break
          }
        }
        if (targetIdx >= 0) {
          messages[targetIdx] = { ...messages[targetIdx], content: { text }, streaming }
        }
        return { ...conv, messages }
      }),
    })),

  addConversation: (conv) =>
    set((state) => {
      if (state.conversations.find((c) => c.id === conv.id)) return state
      return { conversations: [...state.conversations, { ...conv, updatedAt: Date.now(), unread: false, pinned: false }] }
    }),

  removeConversation: (convId) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== convId),
      activeConversationId: state.activeConversationId === convId ? 'conv_pm' : state.activeConversationId,
    })),

  getActiveConversation: () => {
    const state = get()
    return state.conversations.find((c) => c.id === state.activeConversationId)
  },

  /** Fetch conversations from backend API. Falls back to hardcoded defaults on error. */
  fetchConversations: async () => {
    try {
      const resp = await fetch('/api/conversations')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      // Backend may return array or { conversations: [...] }
      const list = Array.isArray(data) ? data : (data.conversations || [])
      if (list.length > 0) {
        set({
          conversations: list.map(mapConversation),
          activeConversationId: list[0]?.id || 'conv_pm',
        })
      } else {
        set({ conversations: FALLBACK_CONVERSATIONS, activeConversationId: 'conv_pm' })
      }
    } catch (e) {
      console.warn('Failed to fetch conversations from backend, using fallback:', e)
      set({ conversations: FALLBACK_CONVERSATIONS, activeConversationId: 'conv_pm' })
    }
  },
}))

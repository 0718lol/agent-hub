import { create } from 'zustand'
import { useTabStore } from './tabStore'

function generateConvName(text) {
  if (!text || !text.trim()) return null
  const cleaned = text.trim().replace(/[\n\r]+/g, ' ').slice(0, 30)
  return cleaned.length > 20 ? cleaned.slice(0, 20) + '...' : cleaned
}

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
    pinned: Boolean(c.pinned),
    archived: Boolean(c.archived),
    sortOrder: c.sort_order ?? 0,
    goal: {
      objective: c.goal_objective || null,
      stage: c.goal_stage || 'not_started',
      latestDeliverable: c.goal_latest_deliverable || null,
      latestArtifactId: c.goal_latest_artifact_id || null,
      pendingDecision: c.goal_pending_decision || null,
      nextAction: c.goal_next_action || null,
    },
    unread: false,
    updatedAt: c.updated_at || c.created_at ? new Date(c.updated_at || c.created_at).getTime() : Date.now(),
  }
}

const FALLBACK_CONVERSATIONS = [
  { id: 'conv_pm', type: 'single', agentId: 'agent_pm', name: 'PM 小助手', avatar: null, role: '需求分析与任务拆解', messages: [], pinned: false, unread: false, updatedAt: Date.now() },
  { id: 'conv_frontend', type: 'single', agentId: 'agent_frontend', name: '前端工程师', avatar: null, role: 'React 组件与样式开发', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 1000 },
  { id: 'conv_backend', type: 'single', agentId: 'agent_backend', name: '后端工程师', avatar: null, role: 'API 接口与数据模型', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 2000 },
  { id: 'conv_tester', type: 'single', agentId: 'agent_tester', name: '测试工程师', avatar: null, role: '测试用例与 Bug 分析', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 3000 },
  { id: 'conv_devops', type: 'single', agentId: 'agent_devops', name: '运维工程师', avatar: null, role: 'Docker 部署与 CI/CD', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 4000 },
  { id: 'conv_designer', type: 'single', agentId: 'agent_designer', name: '设计顾问', avatar: null, role: 'UI/UX 设计建议', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 5000 },
  { id: 'conv_builder', type: 'single', agentId: 'agent_builder', name: 'Agent 工坊', avatar: null, role: '对话式创建自定义 Agent', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 6000 },
  { id: 'conv_group_demo', type: 'group', name: 'Demo 项目群', avatar: null, agents: ['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer'], messages: [], pinned: false, unread: false, updatedAt: Date.now() - 7000 },
]

async function patchConversation(conversationId, updates) {
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
}

export const useChatStore = create((set, get) => ({
  conversations: FALLBACK_CONVERSATIONS,
  activeConversationId: 'conv_pm',
  _ownerId: null,
  typingAgents: {},
  thinkingAgents: {},
  generatingConvs: new Set(),
  allRead: {},
  pinnedMessages: {},
  hasOlderMessages: {},

  setOwner: (ownerId) => {
    if (!ownerId || get()._ownerId === ownerId) return
    set({
      conversations: FALLBACK_CONVERSATIONS,
      activeConversationId: 'conv_pm',
      typingAgents: {},
      thinkingAgents: {},
      generatingConvs: new Set(),
      allRead: {},
      pinnedMessages: {},
      hasOlderMessages: {},
      _ownerId: ownerId,
    })
  },

  setActiveConversation: (id) => set({ activeConversationId: id }),

  togglePin: async (conversationId) => {
    const conversation = get().conversations.find((item) => item.id === conversationId)
    if (!conversation) return
    const pinned = !conversation.pinned
    set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, pinned } : item) }))
    try {
      await patchConversation(conversationId, { pinned })
    } catch (error) {
      set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, pinned: !pinned } : item) }))
      console.error('Failed to pin conversation:', error)
    }
  },

  archiveConversation: async (conversationId) => {
    set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, archived: true } : item) }))
    try {
      await patchConversation(conversationId, { archived: true })
    } catch (error) {
      set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, archived: false } : item) }))
      console.error('Failed to archive conversation:', error)
    }
  },

  renameConversation: async (conversationId, newName) => {
    const previous = get().conversations.find((item) => item.id === conversationId)?.name
    set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, name: newName } : item) }))
    try {
      await patchConversation(conversationId, { name: newName })
      useTabStore.getState().updateTabTitle(conversationId, newName)
    } catch (error) {
      set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, name: previous } : item) }))
      console.error('Failed to rename conversation:', error)
    }
  },

  reorderConversations: (fromId, toId) => set((state) => {
    const list = [...state.conversations]
    const fromIndex = list.findIndex((item) => item.id === fromId)
    const toIndex = list.findIndex((item) => item.id === toId)
    if (fromIndex < 0 || toIndex < 0) return state
    const [moved] = list.splice(fromIndex, 1)
    list.splice(toIndex, 0, moved)
    const conversations = list.map((item, index) => ({ ...item, sortOrder: index }))
    fetch('/api/conversations/order', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: conversations.map((item) => item.id) }),
    }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
    }).catch((error) => console.error('Failed to reorder conversations:', error))
    return { conversations }
  }),

  togglePinMessage: async (conversationId, messageId) => {
    const message = get().conversations.find((item) => item.id === conversationId)?.messages.find((item) => item.id === messageId)
    if (!message) return
    const pinned = !message.pinned
    const applyPinned = (value) => set((state) => {
      const current = state.pinnedMessages[conversationId] || []
      const next = value ? [...new Set([...current, messageId])] : current.filter((id) => id !== messageId)
      return {
        pinnedMessages: { ...state.pinnedMessages, [conversationId]: next },
        conversations: state.conversations.map((conversation) => conversation.id === conversationId
          ? { ...conversation, messages: conversation.messages.map((item) => item.id === messageId ? { ...item, pinned: value } : item) }
          : conversation),
      }
    })
    applyPinned(pinned)
    if (typeof messageId !== 'number') return
    try {
      const response = await fetch(`/api/conversations/${conversationId}/messages/${messageId}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pinned }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
    } catch (error) {
      applyPinned(!pinned)
      console.error('Failed to pin message:', error)
    }
  },

  setTyping: (conversationId, agentId, isTyping) => set((state) => {
    const current = new Set(state.typingAgents[conversationId] || [])
    if (isTyping) current.add(agentId)
    else current.delete(agentId)
    return { typingAgents: { ...state.typingAgents, [conversationId]: current } }
  }),

  setThinking: (conversationId, agentId, text) => set((state) => {
    const convThinking = { ...(state.thinkingAgents[conversationId] || {}) }
    if (text) convThinking[agentId] = text
    else delete convThinking[agentId]
    return { thinkingAgents: { ...state.thinkingAgents, [conversationId]: convThinking } }
  }),

  setGenerating: (conversationId, isGenerating) => set((state) => {
    const next = new Set(state.generatingConvs)
    if (isGenerating) next.add(conversationId)
    else next.delete(conversationId)
    return { generatingConvs: next }
  }),

  markRead: (conversationId) => set((state) => ({
    allRead: { ...state.allRead, [conversationId]: true },
    conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, unread: false } : item),
  })),

  markSent: (conversationId) => set((state) => ({ allRead: { ...state.allRead, [conversationId]: false } })),

  loadMessages: async (conversationId) => {
    try {
      const response = await fetch(`/api/conversations/${conversationId}/messages`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const messages = await response.json()
      set((state) => ({
        conversations: state.conversations.map((conversation) => conversation.id === conversationId ? { ...conversation, messages } : conversation),
        pinnedMessages: { ...state.pinnedMessages, [conversationId]: messages.filter((message) => message.pinned).map((message) => message.id) },
        hasOlderMessages: { ...state.hasOlderMessages, [conversationId]: messages.length === 100 },
      }))
    } catch (error) {
      console.error('Failed to load messages:', error)
    }
  },

  loadOlderMessages: async (conversationId) => {
    const conversation = get().conversations.find((item) => item.id === conversationId)
    const beforeId = conversation?.messages.find((message) => typeof message.id === 'number')?.id
    if (!beforeId) return
    try {
      const response = await fetch(`/api/conversations/${conversationId}/messages?limit=100&before_id=${beforeId}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const older = await response.json()
      set((state) => ({
        conversations: state.conversations.map((item) => item.id === conversationId
          ? { ...item, messages: [...older, ...item.messages.filter((message) => !older.some((old) => old.id === message.id))] }
          : item),
        pinnedMessages: {
          ...state.pinnedMessages,
          [conversationId]: [...new Set([...(state.pinnedMessages[conversationId] || []), ...older.filter((message) => message.pinned).map((message) => message.id)])],
        },
        hasOlderMessages: { ...state.hasOlderMessages, [conversationId]: older.length === 100 },
      }))
    } catch (error) {
      console.error('Failed to load older messages:', error)
    }
  },

  addMessage: (conversationId, message) => {
    const conversation = get().conversations.find((item) => item.id === conversationId)
    const autoName = message.sender === 'user' && conversation?.messages.length === 0
      ? generateConvName(message.content?.text || '')
      : null
    set((state) => ({
      conversations: state.conversations.map((item) => {
        if (item.id !== conversationId) return item
        if (message.id && item.messages.some((existing) => existing.id === message.id)) return item
        const id = message.id || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2))
        return {
          ...item,
          name: autoName || item.name,
          messages: [...item.messages, { ...message, id, timestamp: message.timestamp || new Date().toISOString() }],
          updatedAt: Date.now(),
          unread: message.sender !== 'user' && conversationId !== state.activeConversationId,
        }
      }),
    }))
    if (autoName) get().renameConversation(conversationId, autoName)
  },

  clearMessages: (conversationId) => set((state) => ({
    conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, messages: [], preview: '' } : item),
    typingAgents: { ...state.typingAgents, [conversationId]: new Set() },
    thinkingAgents: { ...state.thinkingAgents, [conversationId]: {} },
    pinnedMessages: { ...state.pinnedMessages, [conversationId]: [] },
  })),

  deleteMessage: async (conversationId, messageId) => {
    const previous = get().conversations.find((item) => item.id === conversationId)?.messages || []
    set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, messages: item.messages.filter((message) => message.id !== messageId) } : item) }))
    if (typeof messageId !== 'number') return
    try {
      const response = await fetch(`/api/conversations/${conversationId}/messages/${messageId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
    } catch (error) {
      set((state) => ({ conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, messages: previous } : item) }))
      console.error('Failed to delete message:', error)
    }
  },

  updateLastAgentMessage: (conversationId, senderId, text, streaming) => set((state) => ({
    conversations: state.conversations.map((conversation) => {
      if (conversation.id !== conversationId) return conversation
      const messages = [...conversation.messages]
      let targetIndex = -1
      for (let index = messages.length - 1; index >= 0; index--) {
        if (messages[index].sender === senderId && messages[index].streaming) {
          targetIndex = index
          break
        }
      }
      if (targetIndex >= 0) messages[targetIndex] = { ...messages[targetIndex], content: { text }, streaming }
      return { ...conversation, messages }
    }),
  })),

  addConversation: (conversation) => {
    set((state) => {
      if (state.conversations.some((item) => item.id === conversation.id)) return state
      return { conversations: [...state.conversations, { ...conversation, updatedAt: Date.now(), unread: false, pinned: false }] }
    })
    return fetch('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: conversation.id,
        type: conversation.type || 'single',
        name: conversation.name,
        avatar: conversation.avatar || null,
        agent_id: conversation.agentId || null,
        agents: conversation.agents || null,
        preview: conversation.preview || conversation.role || '',
      }),
    }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response
    })
  },

  removeConversation: (conversationId) => set((state) => {
    const remaining = state.conversations.filter((item) => item.id !== conversationId)
    return {
      conversations: remaining,
      activeConversationId: state.activeConversationId === conversationId ? (remaining[0]?.id || 'conv_pm') : state.activeConversationId,
    }
  }),

  updateConversation: (conversationId, updates) => set((state) => ({
    conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, ...updates } : item),
  })),

  updateGoal: async (conversationId, updates) => {
    const previous = get().conversations.find((item) => item.id === conversationId)?.goal || {}
    const goal = { ...previous, ...updates }
    set((state) => ({
      conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, goal } : item),
    }))
    const payload = {
      objective: goal.objective || null,
      stage: goal.stage || 'not_started',
      latest_deliverable: goal.latestDeliverable || null,
      latest_artifact_id: goal.latestArtifactId || null,
      pending_decision: goal.pendingDecision || null,
      next_action: goal.nextAction || null,
    }
    try {
      const response = await fetch(`/api/conversations/${conversationId}/goal`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return true
    } catch (error) {
      set((state) => ({
        conversations: state.conversations.map((item) => item.id === conversationId ? { ...item, goal: previous } : item),
      }))
      console.error('Failed to update conversation goal:', error)
      return false
    }
  },

  initializeGoal: (conversationId, objective) => {
    const conversation = get().conversations.find((item) => item.id === conversationId)
    if (conversation?.goal?.objective || !objective?.trim()) return
    get().updateGoal(conversationId, {
      objective: objective.trim().slice(0, 2000),
      stage: 'planning',
      nextAction: '等待 Agent 分析并执行',
    })
  },

  getActiveConversation: () => get().conversations.find((item) => item.id === get().activeConversationId),

  fetchConversations: async () => {
    const ownerId = get()._ownerId
    try {
      const response = await fetch('/api/conversations')
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      const list = Array.isArray(data) ? data : (data.conversations || [])
      if (get()._ownerId !== ownerId) return
      if (list.length > 0) {
        set({ conversations: list.map(mapConversation), activeConversationId: list[0]?.id || 'conv_pm' })
      } else {
        set({ conversations: [], activeConversationId: 'conv_pm' })
      }
    } catch (error) {
      if (get()._ownerId !== ownerId) return
      console.warn('Failed to fetch conversations from backend, using fallback:', error)
      set({ conversations: FALLBACK_CONVERSATIONS, activeConversationId: 'conv_pm' })
    }
  },
}))

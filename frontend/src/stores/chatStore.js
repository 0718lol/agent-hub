import { create } from 'zustand'

const INITIAL_CONVERSATIONS = [
  { id: 'conv_pm', type: 'single', agentId: 'agent_pm', name: 'PM 小助手', avatar: '📋', messages: [], preview: '需求分析与任务拆解' },
  { id: 'conv_frontend', type: 'single', agentId: 'agent_frontend', name: '前端工程师', avatar: '🎨', messages: [], preview: 'React 组件与样式开发' },
  { id: 'conv_backend', type: 'single', agentId: 'agent_backend', name: '后端工程师', avatar: '⚙️', messages: [], preview: 'API 接口与数据模型' },
  { id: 'conv_tester', type: 'single', agentId: 'agent_tester', name: '测试工程师', avatar: '🧪', messages: [], preview: '测试用例与 Bug 分析' },
  { id: 'conv_devops', type: 'single', agentId: 'agent_devops', name: '运维工程师', avatar: '🚀', messages: [], preview: 'Docker 部署与 CI/CD' },
  { id: 'conv_designer', type: 'single', agentId: 'agent_designer', name: '设计顾问', avatar: '🎯', messages: [], preview: 'UI/UX 设计建议' },
  { id: 'conv_group_demo', type: 'group', name: 'Demo 项目群', avatar: '💬', agents: ['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer'], messages: [], preview: '多 Agent 协作演示' },
]

export const useChatStore = create((set, get) => ({
  conversations: INITIAL_CONVERSATIONS,
  activeConversationId: 'conv_pm',
  typingAgents: {},  // { conversationId: Set<agentId> }
  thinkingAgents: {}, // { [convId]: { [agentId]: "thinking text" } }
  generatingConvs: new Set(), // Set<conversationId>
  allRead: {},       // { conversationId: boolean }

  setActiveConversation: (id) => set({ activeConversationId: id }),

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
      if (text) {
        convThinking[agentId] = text
      } else {
        delete convThinking[agentId]
      }
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
            ? { ...conv, messages, preview: messages.length > 0 ? messages[messages.length - 1].content?.text?.slice(0, 30) : conv.preview }
            : conv
        ),
      }))
    } catch (e) {
      console.error('Failed to load messages:', e)
    }
  },

  addMessage: (conversationId, message) =>
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages: [...conv.messages, { ...message, id: Date.now() + Math.random(), timestamp: new Date().toISOString() }],
              preview: message.content?.text?.slice(0, 30) || conv.preview,
            }
          : conv
      ),
    })),

  updateLastAgentMessage: (conversationId, senderId, text, streaming) =>
    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv
        const messages = [...conv.messages]
        const lastIdx = messages.length - 1
        if (lastIdx >= 0 && messages[lastIdx].sender === senderId && messages[lastIdx].streaming) {
          messages[lastIdx] = { ...messages[lastIdx], content: { text }, streaming }
        }
        return { ...conv, messages }
      }),
    })),

  getActiveConversation: () => {
    const state = get()
    return state.conversations.find((c) => c.id === state.activeConversationId)
  },
}))

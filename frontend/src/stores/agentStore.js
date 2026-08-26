import { create } from 'zustand'
import { useChatStore } from './chatStore'
import { useTabStore } from './tabStore'

const PRESET_AGENTS = [
  { agent_id: 'agent_pm', name: 'PM 小助手', role: '产品经理 · 需求分析与任务拆解', status: 'idle', agent_type: 'self' },
  { agent_id: 'claude_code', name: 'Claude Code', role: 'Anthropic 最强代码 Agent · 原生工具调用', status: 'idle', agent_type: 'external', adapter_type: 'claude', avatar: '/avatars/claude-code.png' },
  { agent_id: 'codex', name: 'Codex', role: '本机 Codex CLI · 工作区代码 Agent', status: 'idle', agent_type: 'external', adapter_type: 'codex', avatar: '/avatars/codex.png' },
  { agent_id: 'coze', name: 'Coze', role: '字节跳动 Agent 平台 · 插件与工作流', status: 'idle', agent_type: 'external', adapter_type: 'coze', avatar: '/avatars/coze.png' },
  { agent_id: 'self_deployed', name: '本地 Agent', role: '自部署 Agent · OpenCode/自定义 HTTP 服务', status: 'idle', agent_type: 'external', adapter_type: 'self_deployed', avatar: null },
  { agent_id: 'agent_frontend', name: '前端工程师', role: '前端开发 · React/TypeScript', status: 'idle', agent_type: 'self' },
  { agent_id: 'agent_backend', name: '后端工程师', role: '后端开发 · API/数据库', status: 'idle', agent_type: 'self' },
  { agent_id: 'agent_tester', name: '测试工程师', role: '测试 · 用例设计/Bug追踪', status: 'idle', agent_type: 'self' },
  { agent_id: 'agent_devops', name: '运维工程师', role: '运维部署 · Docker/CI/CD', status: 'idle', agent_type: 'self' },
  { agent_id: 'agent_designer', name: '设计顾问', role: 'UI/UX 设计 · 交互体验', status: 'idle', agent_type: 'self' },
  { agent_id: 'agent_builder', name: 'Agent 工坊', role: '对话式创建自定义 Agent', status: 'idle', agent_type: 'self' },
]
const DELETED_PRESETS_KEY = 'agent-hub-deleted-presets'

function deletedPresetsKey(ownerId) {
  return `${DELETED_PRESETS_KEY}:${ownerId}`
}

function loadDeletedPresets(ownerId) {
  try {
    const key = deletedPresetsKey(ownerId)
    let raw = localStorage.getItem(key)
    if (!raw) {
      raw = localStorage.getItem(DELETED_PRESETS_KEY)
      if (raw) {
        localStorage.setItem(key, raw)
        localStorage.removeItem(DELETED_PRESETS_KEY)
      }
    }
    return JSON.parse(raw || '[]')
  } catch (_e) { return [] }
}

export const useAgentStore = create((set, get) => ({
  agents: PRESET_AGENTS,
  deletedPresetIds: [],
  adapterStatus: {},  // { agent_id: { configured: bool, error: string } }
  _ownerId: null,

  setOwner: (ownerId) => {
    if (!ownerId || get()._ownerId === ownerId) return
    set({
      agents: PRESET_AGENTS,
      deletedPresetIds: loadDeletedPresets(ownerId),
      adapterStatus: {},
      _ownerId: ownerId,
    })
  },

  setAgentStatus: (agentId, status) =>
    set((state) => ({
      agents: state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, status } : a
      ),
    })),

  getAgent: (agentId) => get().agents.find((a) => a.agent_id === agentId),

  // 加载后端自定义 Agent
  loadCustomAgents: async () => {
    const ownerId = get()._ownerId
    try {
      const resp = await fetch('/api/agents/custom')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      set((state) => {
        if (state._ownerId !== ownerId) return {}
        const existingIds = new Set(state.agents.map((a) => a.agent_id))
        const newcomers = data.filter((a) => !existingIds.has(a.agent_id))
        if (newcomers.length === 0) return {}
        return { agents: [...state.agents, ...newcomers] }
      })
    } catch (_e) { /* ignore fetch errors */ }
  },

  // 添加本地自定义 Agent（创建成功后调用）
  addCustomAgent: (agent) =>
    set((state) => ({ agents: [...state.agents, { ...agent, status: 'idle' }] })),

  // Fetch custom agents from backend API for full metadata
  fetchAgents: async () => {
    try {
      // Load custom agents with full metadata from backend
      await get().loadCustomAgents()
    } catch (e) {
      console.warn('Failed to fetch agents from backend:', e)
    }
  },

  // 获取适配器状态
  fetchAdapterStatus: async () => {
    try {
      const resp = await fetch('/api/adapters')
      const data = await resp.json()
      const statusMap = {}
      for (const adapter of (data.adapters || [])) {
        statusMap[adapter.agent_id || adapter.name] = adapter
      }
      set({ adapterStatus: statusMap })
    } catch {}
  },

  // 检查外部 Agent 是否已配置
  isAdapterConfigured: (agentId) => {
    const status = get().adapterStatus[agentId]
    return status?.configured ?? false
  },

  // 删除 Agent
  //  预设 Agent → 标记为已删除（本地隐藏，localStorage 记录）
  //  自定义 Agent → 从列表移除 + 调后端 DELETE
  removeAgent: async (agentId) => {
    const agent = get().agents.find((item) => item.agent_id === agentId)
    const isCustom = Boolean(agent?.custom)
    if (isCustom) {
      const response = await fetch(`/api/agents/custom/${agentId}`, { method: 'DELETE' })
      if (!response.ok) return false
    }

    // 关闭该 Agent 相关的所有标签
    const convIdPrefix = `conv_${agentId}`
    const tabs = useTabStore.getState().openTabs
    for (const tab of tabs) {
      if (tab.convId === convIdPrefix || tab.convId.startsWith(convIdPrefix + '_')) {
        useTabStore.getState().closeTab(tab.id)
      }
    }

    set((state) => {
      if (isCustom) {
        // 同步删除该 Agent 的会话
        useChatStore.getState().removeConversation(convIdPrefix)
        return { agents: state.agents.filter((a) => a.agent_id !== agentId) }
      }
      const newDeleted = [...new Set([...state.deletedPresetIds, agentId])]
      try {
        if (state._ownerId) localStorage.setItem(deletedPresetsKey(state._ownerId), JSON.stringify(newDeleted))
      } catch (_e) { /* ignore */ }
      return { deletedPresetIds: newDeleted }
    })
    return true
  },
}))

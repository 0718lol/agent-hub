import { create } from 'zustand'

const AGENTS = [
  { agent_id: 'agent_pm', name: 'PM 小助手', avatar: '📋', role: '产品经理', status: 'idle' },
  { agent_id: 'agent_frontend', name: '前端工程师', avatar: '🎨', role: '前端开发', status: 'idle' },
  { agent_id: 'agent_backend', name: '后端工程师', avatar: '⚙️', role: '后端开发', status: 'idle' },
  { agent_id: 'agent_tester', name: '测试工程师', avatar: '🧪', role: '测试', status: 'idle' },
  { agent_id: 'agent_devops', name: '运维工程师', avatar: '🚀', role: '运维部署', status: 'idle' },
  { agent_id: 'agent_designer', name: '设计顾问', avatar: '🎯', role: 'UI/UX 设计', status: 'idle' },
]

export const useAgentStore = create((set) => ({
  agents: AGENTS,
  setAgentStatus: (agentId, status) =>
    set((state) => ({
      agents: state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, status } : a
      ),
    })),
  getAgent: (agentId) => AGENTS.find((a) => a.agent_id === agentId),
}))

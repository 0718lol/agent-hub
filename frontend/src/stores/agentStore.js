import { create } from 'zustand'

const AGENTS = [
  { agent_id: 'agent_pm', name: 'PM 小助手', role: '产品经理 · 需求分析与任务拆解', status: 'idle' },
  { agent_id: 'agent_frontend', name: '前端工程师', role: '前端开发 · React/TypeScript', status: 'idle' },
  { agent_id: 'agent_backend', name: '后端工程师', role: '后端开发 · API/数据库', status: 'idle' },
  { agent_id: 'agent_tester', name: '测试工程师', role: '测试 · 用例设计/Bug追踪', status: 'idle' },
  { agent_id: 'agent_devops', name: '运维工程师', role: '运维部署 · Docker/CI/CD', status: 'idle' },
  { agent_id: 'agent_designer', name: '设计顾问', role: 'UI/UX 设计 · 交互体验', status: 'idle' },
]

export const useAgentStore = create((set, get) => ({
  agents: AGENTS,
  setAgentStatus: (agentId, status) =>
    set((state) => ({
      agents: state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, status } : a
      ),
    })),
  getAgent: (agentId) => AGENTS.find((a) => a.agent_id === agentId),
}))

import { create } from 'zustand'

const DEFAULT_TASKS = [
  { id: 1, title: '设计页面 UI', assignee: 'agent_designer', status: 'todo' },
  { id: 2, title: '实现前端组件', assignee: 'agent_frontend', status: 'todo' },
  { id: 3, title: '实现后端 API', assignee: 'agent_backend', status: 'todo' },
  { id: 4, title: '编写测试用例', assignee: 'agent_tester', status: 'todo' },
  { id: 5, title: '配置部署方案', assignee: 'agent_devops', status: 'todo' },
]

const DEFAULT_DAG_NODES = [
  { id: 'user', label: '用户', iconKey: 'user', x: 200, y: 30, status: 'idle' },
  { id: 'agent_pm', label: 'PM', iconKey: 'agent_pm', x: 200, y: 130, status: 'idle' },
  { id: 'agent_designer', label: '设计', iconKey: 'agent_designer', x: 60, y: 250, status: 'idle' },
  { id: 'agent_frontend', label: '前端', iconKey: 'agent_frontend', x: 160, y: 250, status: 'idle' },
  { id: 'agent_backend', label: '后端', iconKey: 'agent_backend', x: 260, y: 250, status: 'idle' },
  { id: 'agent_tester', label: '测试', iconKey: 'agent_tester', x: 360, y: 250, status: 'idle' },
  { id: 'agent_devops', label: '运维', iconKey: 'agent_devops', x: 340, y: 130, status: 'idle' },
]

const DEFAULT_DAG_EDGES = [
  { from: 'user', to: 'agent_pm' },
  { from: 'agent_pm', to: 'agent_designer' },
  { from: 'agent_pm', to: 'agent_frontend' },
  { from: 'agent_pm', to: 'agent_backend' },
  { from: 'agent_pm', to: 'agent_tester' },
  { from: 'agent_pm', to: 'agent_devops' },
]

export const useCanvasStore = create((set) => ({
  _ownerId: null,
  setOwner: (ownerId) => set((state) => {
    if (!ownerId || state._ownerId === ownerId) return {}
    return {
      _ownerId: ownerId,
      activeTab: 'dag',
      slidePanelOpen: false,
      slidePanelContent: 'code',
      slidePanelTab: 'code',
      previewHtml: null,
      generatedCode: null,
      previousCode: '',
      isDeploying: false,
      deployLogs: [],
      deployedUrl: '',
      deployResultType: 'site',
      deployTarget: 'web',
      deployJobId: '',
      deployStatus: 'idle',
      tasks: DEFAULT_TASKS.map((task) => ({ ...task })),
      dagNodes: DEFAULT_DAG_NODES.map((node) => ({ ...node })),
      dagEdges: DEFAULT_DAG_EDGES.map((edge) => ({ ...edge })),
    }
  }),

  activeTab: 'dag',
  setActiveTab: (tab) => set({ activeTab: tab }),

  // Slide panel state
  slidePanelOpen: false,
  slidePanelContent: 'code', // 'code' | 'dag' | 'task' | 'tools' | 'knowledge'
  slidePanelTab: 'code',
  slidePanelWidth: (() => {
    try { const v = localStorage.getItem('agent-hub-slide-panel-width'); return v ? parseInt(v) : 380 }
    catch (_e) { return 380 }
  })(),
  toggleSlidePanel: (content) => set((s) => {
    if (s.slidePanelOpen && s.slidePanelContent === content) {
      return { slidePanelOpen: false }
    }
    return { slidePanelOpen: true, slidePanelContent: content }
  }),
  setSlidePanelTab: (tab) => set({ slidePanelTab: tab }),
  setSlidePanelWidth: (width) => {
    try { localStorage.setItem('agent-hub-slide-panel-width', String(width)) } catch (_e) { /* ignore */ }
    set({ slidePanelWidth: width })
  },

  previewHtml: null,
  setPreviewHtml: (html) => set({ previewHtml: html }),

  generatedCode: null,
  previousCode: '',
  setGeneratedCode: (language, code) =>
    set((state) => ({
      previousCode: state.generatedCode?.code || '',
      generatedCode: { language, code },
    })),

  isDeploying: false,
  deployLogs: [],
  deployedUrl: '',
  deployResultType: 'site',
  deployTarget: 'web',
  deployJobId: '',
  deployStatus: 'idle',

  startDeploy: () =>
    set({ isDeploying: true, deployStatus: 'running', deployLogs: [], deployedUrl: '', deployResultType: 'site', deployJobId: '' }),
  markDeployRunning: () => set({ isDeploying: true, deployStatus: 'running' }),
  setDeployJobId: (jobId) => set({ deployJobId: jobId }),
  appendDeployLog: (log) =>
    set((state) => ({ deployLogs: [...state.deployLogs, log] })),
  finishDeploy: (url, resultType = 'site', target = 'web') =>
    set({ isDeploying: false, deployStatus: 'success', deployedUrl: url, deployResultType: resultType, deployTarget: target }),
  failDeploy: () =>
    set({ isDeploying: false, deployStatus: 'failed' }),
  cancelDeploy: () =>
    set({ isDeploying: false, deployStatus: 'cancelled' }),
  resetDeploy: () =>
    set({ isDeploying: false, deployStatus: 'idle', deployLogs: [], deployedUrl: '', deployResultType: 'site', deployJobId: '' }),

  tasks: DEFAULT_TASKS.map((task) => ({ ...task })),
  moveTask: (taskId, newStatus) =>
    set((state) => ({ tasks: state.tasks.map((t) => t.id === taskId ? { ...t, status: newStatus } : t) })),
  addTask: (task) =>
    set((state) => ({ tasks: [...state.tasks, { ...task, id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2) }] })),
  deleteTask: (taskId) =>
    set((state) => ({ tasks: state.tasks.filter((t) => t.id !== taskId) })),
  changeTaskStatus: (taskId, newStatus) =>
    set((state) => ({ tasks: state.tasks.map((t) => t.id === taskId ? { ...t, status: newStatus } : t) })),
  updateTaskByAgent: (agentId, status) =>
    set((state) => ({ tasks: state.tasks.map((t) => t.assignee === agentId ? { ...t, status } : t) })),

  dagNodes: DEFAULT_DAG_NODES.map((node) => ({ ...node })),
  dagEdges: DEFAULT_DAG_EDGES.map((edge) => ({ ...edge })),
  setNodeStatus: (nodeId, status) =>
    set((state) => ({ dagNodes: state.dagNodes.map((n) => n.id === nodeId ? { ...n, status } : n) })),

  // Fetch DAG topology from backend agents list
  fetchDAGFromBackend: async () => {
    try {
      const resp = await fetch('/api/health')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      if (!data.agents || data.agents.length === 0) return
      const agentIds = data.agents
      // Build DAG nodes from backend agents
      const newNodes = [
        { id: 'user', label: '用户', iconKey: 'user', x: 200, y: 30, status: 'idle' },
        ...agentIds.map((id, i) => ({
          id, label: id.replace('agent_', '').toUpperCase(), iconKey: id,
          x: 60 + (i % 5) * 100, y: 130 + Math.floor(i / 5) * 120, status: 'idle'
        }))
      ]
      const newEdges = agentIds.map((id) => ({ from: 'agent_pm', to: id }))
      set({ dagNodes: newNodes, dagEdges: newEdges })
    } catch (e) {
      console.warn('Failed to fetch DAG from backend:', e)
    }
  },
}))

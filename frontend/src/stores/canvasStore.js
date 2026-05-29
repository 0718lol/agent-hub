import { create } from 'zustand'

export const useCanvasStore = create((set) => ({
  activeTab: 'dag',
  setActiveTab: (tab) => set({ activeTab: tab }),

  // Slide panel state
  slidePanelOpen: false,
  slidePanelContent: 'code', // 'code' | 'dag' | 'task'
  slidePanelTab: 'code',
  slidePanelWidth: (() => {
    try { const v = localStorage.getItem('agent-hub-slide-panel-width'); return v ? parseInt(v) : 380 }
    catch { return 380 }
  })(),
  toggleSlidePanel: (content) => set((s) => {
    if (s.slidePanelOpen && s.slidePanelContent === content) {
      return { slidePanelOpen: false }
    }
    return { slidePanelOpen: true, slidePanelContent: content }
  }),
  setSlidePanelTab: (tab) => set({ slidePanelTab: tab }),
  setSlidePanelWidth: (width) => {
    try { localStorage.setItem('agent-hub-slide-panel-width', String(width)) } catch {}
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
  deployStatus: 'idle',

  startDeploy: () =>
    set({ isDeploying: true, deployStatus: 'running', deployLogs: [], deployedUrl: '' }),
  appendDeployLog: (log) =>
    set((state) => ({ deployLogs: [...state.deployLogs, log] })),
  finishDeploy: (url) =>
    set({ isDeploying: false, deployStatus: 'success', deployedUrl: url }),
  failDeploy: () =>
    set({ isDeploying: false, deployStatus: 'failed' }),
  resetDeploy: () =>
    set({ isDeploying: false, deployStatus: 'idle', deployLogs: [], deployedUrl: '' }),

  tasks: [
    { id: 1, title: '设计页面 UI', assignee: 'agent_designer', status: 'todo' },
    { id: 2, title: '实现前端组件', assignee: 'agent_frontend', status: 'todo' },
    { id: 3, title: '实现后端 API', assignee: 'agent_backend', status: 'todo' },
    { id: 4, title: '编写测试用例', assignee: 'agent_tester', status: 'todo' },
    { id: 5, title: '配置部署方案', assignee: 'agent_devops', status: 'todo' },
  ],
  moveTask: (taskId, newStatus) =>
    set((state) => ({ tasks: state.tasks.map((t) => t.id === taskId ? { ...t, status: newStatus } : t) })),
  addTask: (task) =>
    set((state) => ({ tasks: [...state.tasks, { ...task, id: Date.now() }] })),
  updateTaskByAgent: (agentId, status) =>
    set((state) => ({ tasks: state.tasks.map((t) => t.assignee === agentId ? { ...t, status } : t) })),

  dagNodes: [
    { id: 'user', label: '用户', iconKey: 'user', x: 200, y: 30, status: 'idle' },
    { id: 'agent_pm', label: 'PM', iconKey: 'agent_pm', x: 200, y: 130, status: 'idle' },
    { id: 'agent_designer', label: '设计', iconKey: 'agent_designer', x: 60, y: 250, status: 'idle' },
    { id: 'agent_frontend', label: '前端', iconKey: 'agent_frontend', x: 160, y: 250, status: 'idle' },
    { id: 'agent_backend', label: '后端', iconKey: 'agent_backend', x: 260, y: 250, status: 'idle' },
    { id: 'agent_tester', label: '测试', iconKey: 'agent_tester', x: 360, y: 250, status: 'idle' },
    { id: 'agent_devops', label: '运维', iconKey: 'agent_devops', x: 340, y: 130, status: 'idle' },
  ],
  dagEdges: [
    { from: 'user', to: 'agent_pm' },
    { from: 'agent_pm', to: 'agent_designer' },
    { from: 'agent_pm', to: 'agent_frontend' },
    { from: 'agent_pm', to: 'agent_backend' },
    { from: 'agent_pm', to: 'agent_tester' },
    { from: 'agent_pm', to: 'agent_devops' },
  ],
  setNodeStatus: (nodeId, status) =>
    set((state) => ({ dagNodes: state.dagNodes.map((n) => n.id === nodeId ? { ...n, status } : n) })),
}))

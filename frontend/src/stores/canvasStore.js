import { create } from 'zustand'

export const useCanvasStore = create((set) => ({
  activeTab: 'dag',
  setActiveTab: (tab) => set({ activeTab: tab }),

  previewHtml: null,
  setPreviewHtml: (html) => set({ previewHtml: html, activeTab: 'preview' }),

  generatedCode: null,
  setGeneratedCode: (language, code) => set({ generatedCode: { language, code }, activeTab: 'diff' }),

  tasks: [
    { id: 1, title: '设计页面 UI', assignee: 'agent_designer', status: 'todo' },
    { id: 2, title: '实现前端组件', assignee: 'agent_frontend', status: 'todo' },
    { id: 3, title: '实现后端 API', assignee: 'agent_backend', status: 'todo' },
    { id: 4, title: '编写测试用例', assignee: 'agent_tester', status: 'todo' },
    { id: 5, title: '配置部署方案', assignee: 'agent_devops', status: 'todo' },
  ],

  moveTask: (taskId, newStatus) =>
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.id === taskId ? { ...t, status: newStatus } : t
      ),
    })),

  addTask: (task) =>
    set((state) => ({
      tasks: [...state.tasks, { ...task, id: Date.now() }],
    })),

  updateTaskByAgent: (agentId, status) =>
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.assignee === agentId ? { ...t, status } : t
      ),
    })),

  dagNodes: [
    { id: 'user', label: '用户', icon: '👤', x: 200, y: 30, status: 'idle' },
    { id: 'agent_pm', label: 'PM', icon: '📋', x: 200, y: 130, status: 'idle' },
    { id: 'agent_designer', label: '设计', icon: '🎯', x: 60, y: 250, status: 'idle' },
    { id: 'agent_frontend', label: '前端', icon: '🎨', x: 160, y: 250, status: 'idle' },
    { id: 'agent_backend', label: '后端', icon: '⚙️', x: 260, y: 250, status: 'idle' },
    { id: 'agent_tester', label: '测试', icon: '🧪', x: 360, y: 250, status: 'idle' },
    { id: 'agent_devops', label: '运维', icon: '🚀', x: 340, y: 130, status: 'idle' },
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
    set((state) => ({
      dagNodes: state.dagNodes.map((n) =>
        n.id === nodeId ? { ...n, status } : n
      ),
    })),
}))

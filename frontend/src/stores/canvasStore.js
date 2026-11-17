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

const SESSION_KEYS = [
  'previewHtml',
  'streamingHtml',
  'generatedCode',
  'previousCode',
  'isDeploying',
  'deployLogs',
  'deployedUrl',
  'deployResultType',
  'deployTarget',
  'deployJobId',
  'deployStatus',
  'activeDeployJob',
  'tasks',
  'dagNodes',
  'dagEdges',
]

function createDefaultSession(dagTemplate) {
  return {
    previewHtml: null,
    streamingHtml: null,
    generatedCode: null,
    previousCode: '',
    isDeploying: false,
    deployLogs: [],
    deployedUrl: '',
    deployResultType: 'site',
    deployTarget: 'web',
    deployJobId: '',
    deployStatus: 'idle',
    activeDeployJob: null,
    tasks: structuredClone(DEFAULT_TASKS),
    dagNodes: structuredClone(dagTemplate?.nodes || DEFAULT_DAG_NODES),
    dagEdges: structuredClone(dagTemplate?.edges || DEFAULT_DAG_EDGES),
  }
}

function projectActiveFields(state) {
  const projected = {}
  for (const key of SESSION_KEYS) {
    projected[key] = state[key]
  }
  return projected
}

function updateSession(state, targetConvId, updater) {
  const activeId = state.activeConversationId || 'conv_pm'
  const convId = targetConvId || activeId
  const isTargetActive = convId === activeId

  const currentSnapshot = isTargetActive
    ? { ...createDefaultSession(state._dagTemplate), ...(state.sessions[convId] || {}), ...projectActiveFields(state) }
    : { ...createDefaultSession(state._dagTemplate), ...(state.sessions[convId] || {}) }

  const patch = updater(currentSnapshot)
  if (!patch || Object.keys(patch).length === 0) return {}

  const nextSession = { ...currentSnapshot, ...patch }
  const nextSessions = { ...state.sessions, [convId]: nextSession }

  if (isTargetActive) {
    return { ...patch, sessions: nextSessions }
  }
  return { sessions: nextSessions }
}

export const useCanvasStore = create((set, get) => {
  const initialTemplate = {
    nodes: structuredClone(DEFAULT_DAG_NODES),
    edges: structuredClone(DEFAULT_DAG_EDGES),
  }
  const initialSession = createDefaultSession(initialTemplate)

  return {
    _ownerId: null,
    _dagTemplate: initialTemplate,
    activeConversationId: 'conv_pm',
    sessions: { conv_pm: initialSession },

    setOwner: (ownerId) => set((state) => {
      if (!ownerId || state._ownerId === ownerId) return {}
      const freshSession = createDefaultSession(state._dagTemplate)
      return {
        _ownerId: ownerId,
        activeConversationId: 'conv_pm',
        sessions: { conv_pm: freshSession },
        activeTab: 'dag',
        slidePanelOpen: false,
        slidePanelContent: 'code',
        slidePanelTab: 'code',
        ...freshSession,
      }
    }),

    setActiveConversation: (conversationId) => set((state) => {
      if (!conversationId) return {}
      const prevId = state.activeConversationId || 'conv_pm'
      const savedPrev = {
        ...createDefaultSession(state._dagTemplate),
        ...(state.sessions[prevId] || {}),
        ...projectActiveFields(state),
      }
      if (conversationId === prevId) {
        return { sessions: { ...state.sessions, [prevId]: savedPrev } }
      }
      const nextSession = state.sessions[conversationId]
        ? { ...createDefaultSession(state._dagTemplate), ...state.sessions[conversationId] }
        : createDefaultSession(state._dagTemplate)
      return {
        activeConversationId: conversationId,
        sessions: {
          ...state.sessions,
          [prevId]: savedPrev,
          [conversationId]: nextSession,
        },
        ...nextSession,
      }
    }),

    getSession: (conversationId) => {
      const state = get()
      const convId = conversationId || state.activeConversationId || 'conv_pm'
      if (convId === state.activeConversationId) {
        return projectActiveFields(state)
      }
      return state.sessions[convId] || createDefaultSession(state._dagTemplate)
    },

    activeTab: 'dag',
    setActiveTab: (tab) => set({ activeTab: tab }),

    // Slide panel state (workspace UI layout preference)
    slidePanelOpen: false,
    slidePanelContent: 'code', // 'code' | 'dag' | 'task' | 'tools' | 'knowledge'
    slidePanelTab: 'code',
    slidePanelWidth: (() => {
      try { const v = localStorage.getItem('agent-hub-slide-panel-width'); return v ? parseInt(v, 10) : 380 }
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

    ...initialSession,

    setPreviewHtml: (html, conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({ previewHtml: html }))),

    setStreamingHtml: (html, conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({ streamingHtml: html }))),

    clearStreamingHtml: (conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({ streamingHtml: null }))),

    setGeneratedCode: (language, code, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => {
        const normalizedLanguage = String(language || '').toLowerCase()
        const next = {
          previousCode: session.generatedCode?.code || '',
          generatedCode: language == null && code == null ? null : { language, code },
        }
        if (normalizedLanguage === 'html' || normalizedLanguage === 'htm') {
          next.previewHtml = code
        }
        return next
      })),

    startDeploy: (conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({
        isDeploying: true,
        deployStatus: 'running',
        deployLogs: [],
        deployedUrl: '',
        deployResultType: 'site',
        deployJobId: '',
        activeDeployJob: null,
      }))),

    markDeployRunning: (conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({
        isDeploying: true,
        deployStatus: 'running',
      }))),

    setDeployJobId: (jobId, conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({ deployJobId: jobId }))),

    setActiveDeployJob: (job, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        activeDeployJob: typeof job === 'function' ? job(session.activeDeployJob) : job,
      }))),

    appendDeployLog: (log, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        deployLogs: [...session.deployLogs, log],
      }))),

    finishDeploy: (url, resultType = 'site', target = 'web', conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({
        isDeploying: false,
        deployStatus: 'success',
        deployedUrl: url,
        deployResultType: resultType,
        deployTarget: target,
      }))),

    failDeploy: (conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({
        isDeploying: false,
        deployStatus: 'failed',
      }))),

    cancelDeploy: (conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({
        isDeploying: false,
        deployStatus: 'cancelled',
      }))),

    resetDeploy: (conversationId) =>
      set((state) => updateSession(state, conversationId, () => ({
        isDeploying: false,
        deployStatus: 'idle',
        deployLogs: [],
        deployedUrl: '',
        deployResultType: 'site',
        deployJobId: '',
        activeDeployJob: null,
      }))),

    moveTask: (taskId, newStatus, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        tasks: session.tasks.map((t) => (t.id === taskId ? { ...t, status: newStatus } : t)),
      }))),

    addTask: (task, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        tasks: [
          ...session.tasks,
          {
            ...task,
            id:
              typeof crypto !== 'undefined' && crypto.randomUUID
                ? crypto.randomUUID()
                : Date.now().toString(36) + Math.random().toString(36).slice(2),
          },
        ],
      }))),

    deleteTask: (taskId, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        tasks: session.tasks.filter((t) => t.id !== taskId),
      }))),

    changeTaskStatus: (taskId, newStatus, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        tasks: session.tasks.map((t) => (t.id === taskId ? { ...t, status: newStatus } : t)),
      }))),

    updateTaskByAgent: (agentId, status, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        tasks: session.tasks.map((t) => (t.assignee === agentId ? { ...t, status } : t)),
      }))),

    setNodeStatus: (nodeId, status, conversationId) =>
      set((state) => updateSession(state, conversationId, (session) => ({
        dagNodes: session.dagNodes.map((n) => (n.id === nodeId ? { ...n, status } : n)),
      }))),

    // Fetch DAG topology from backend agents list and update template + active/background sessions
    fetchDAGFromBackend: async () => {
      try {
        const resp = await fetch('/api/health')
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data = await resp.json()
        if (!data.agents || data.agents.length === 0) return
        const agentIds = data.agents
        const newNodes = [
          { id: 'user', label: '用户', iconKey: 'user', x: 200, y: 30, status: 'idle' },
          ...agentIds.map((id, i) => ({
            id,
            label: id.replace('agent_', '').toUpperCase(),
            iconKey: id,
            x: 60 + (i % 5) * 100,
            y: 130 + Math.floor(i / 5) * 120,
            status: 'idle',
          })),
        ]
        const newEdges = agentIds.map((id) => ({ from: 'agent_pm', to: id }))
        set((state) => {
          const nextTemplate = {
            nodes: structuredClone(newNodes),
            edges: structuredClone(newEdges),
          }
          const mergeNodes = (prevNodes) => {
            const statusById = new Map((prevNodes || []).map((n) => [n.id, n.status]))
            return newNodes.map((n) => ({ ...n, status: statusById.get(n.id) || 'idle' }))
          }
          const updatedSessions = {}
          for (const [cid, sess] of Object.entries(state.sessions)) {
            updatedSessions[cid] = {
              ...sess,
              dagNodes: mergeNodes(sess.dagNodes),
              dagEdges: structuredClone(newEdges),
            }
          }
          return {
            _dagTemplate: nextTemplate,
            sessions: updatedSessions,
            dagNodes: mergeNodes(state.dagNodes),
            dagEdges: structuredClone(newEdges),
          }
        })
      } catch (e) {
        console.warn('Failed to fetch DAG from backend:', e)
      }
    },
  }
})

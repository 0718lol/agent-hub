import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useCanvasStore } from './canvasStore'

describe('canvasStore', () => {
  beforeEach(() => {
    useCanvasStore.setState({
      activeTab: 'dag',
      slidePanelOpen: false,
      slidePanelContent: 'code',
      slidePanelTab: 'code',
      slidePanelWidth: 380,
      previewHtml: null,
      generatedCode: null,
      previousCode: '',
      projectRevision: 0,
      isDeploying: false,
      deployLogs: [],
      deployedUrl: '',
      deployJobId: '',
      deployResultType: 'site',
      deployTarget: 'web',
      deployStatus: 'idle',
      deployResultVisible: false,
      tasks: [
        { id: 1, title: '设计页面 UI', assignee: 'agent_designer', status: 'todo' },
        { id: 2, title: '实现前端组件', assignee: 'agent_frontend', status: 'todo' },
        { id: 3, title: '实现后端 API', assignee: 'agent_backend', status: 'todo' },
        { id: 4, title: '编写测试用例', assignee: 'agent_tester', status: 'todo' },
        { id: 5, title: '配置部署方案', assignee: 'agent_devops', status: 'todo' },
      ],
      dagNodes: [
        { id: 'user', label: '用户', iconKey: 'user', x: 200, y: 30, status: 'idle' },
        { id: 'agent_pm', label: 'PM', iconKey: 'agent_pm', x: 200, y: 130, status: 'idle' },
      ],
      dagEdges: [
        { from: 'user', to: 'agent_pm' },
      ],
    })
  })

  // ---------- setActiveTab ----------

  it('should set active tab', () => {
    useCanvasStore.getState().setActiveTab('task')
    expect(useCanvasStore.getState().activeTab).toBe('task')
  })

  // ---------- toggleSlidePanel ----------

  it('should open slide panel when closed', () => {
    useCanvasStore.setState({ slidePanelOpen: false })
    useCanvasStore.getState().toggleSlidePanel('dag')
    const state = useCanvasStore.getState()
    expect(state.slidePanelOpen).toBe(true)
    expect(state.slidePanelContent).toBe('dag')
  })

  it('should close slide panel when same content is toggled', () => {
    useCanvasStore.setState({ slidePanelOpen: true, slidePanelContent: 'dag' })
    useCanvasStore.getState().toggleSlidePanel('dag')
    expect(useCanvasStore.getState().slidePanelOpen).toBe(false)
  })

  it('should switch content when different content is toggled while open', () => {
    useCanvasStore.setState({ slidePanelOpen: true, slidePanelContent: 'code' })
    useCanvasStore.getState().toggleSlidePanel('task')
    const state = useCanvasStore.getState()
    expect(state.slidePanelOpen).toBe(true)
    expect(state.slidePanelContent).toBe('task')
  })

  // ---------- setSlidePanelTab ----------

  it('should set slide panel tab', () => {
    useCanvasStore.getState().setSlidePanelTab('dag')
    expect(useCanvasStore.getState().slidePanelTab).toBe('dag')
  })

  // ---------- setPreviewHtml ----------

  it('should set preview HTML', () => {
    useCanvasStore.getState().setPreviewHtml('<h1>Hello</h1>')
    expect(useCanvasStore.getState().previewHtml).toBe('<h1>Hello</h1>')
  })

  // ---------- setGeneratedCode ----------

  it('should set generated code with language', () => {
    useCanvasStore.getState().setGeneratedCode('javascript', 'console.log("hello")')
    const state = useCanvasStore.getState()
    expect(state.generatedCode).toEqual({ language: 'javascript', code: 'console.log("hello")' })
  })

  it('should track previous code when setting new code', () => {
    useCanvasStore.getState().setGeneratedCode('javascript', 'first code')
    useCanvasStore.getState().setGeneratedCode('python', 'second code')
    const state = useCanvasStore.getState()
    expect(state.generatedCode).toEqual({ language: 'python', code: 'second code' })
    expect(state.previousCode).toBe('first code')
  })

  it('should increment project revision for external file updates', () => {
    useCanvasStore.getState().notifyProjectChanged()
    useCanvasStore.getState().notifyProjectChanged()
    expect(useCanvasStore.getState().projectRevision).toBe(2)
  })

  // ---------- Deploy lifecycle ----------

  it('should start deploy', () => {
    useCanvasStore.getState().startDeploy()
    const state = useCanvasStore.getState()
    expect(state.isDeploying).toBe(true)
    expect(state.deployStatus).toBe('running')
    expect(state.deployLogs).toEqual([])
    expect(state.deployedUrl).toBe('')
  })

  it('should append deploy logs', () => {
    useCanvasStore.getState().startDeploy()
    useCanvasStore.getState().appendDeployLog('Building...')
    useCanvasStore.getState().appendDeployLog('Deploying...')
    const state = useCanvasStore.getState()
    expect(state.deployLogs).toEqual(['Building...', 'Deploying...'])
  })

  it('should finish deploy with URL', () => {
    useCanvasStore.getState().startDeploy()
    useCanvasStore.getState().finishDeploy('https://example.com')
    const state = useCanvasStore.getState()
    expect(state.isDeploying).toBe(false)
    expect(state.deployStatus).toBe('success')
    expect(state.deployedUrl).toBe('https://example.com')
    expect(state.deployResultVisible).toBe(true)
  })

  it('should dismiss a completed deploy result without clearing deployment data', () => {
    useCanvasStore.getState().finishDeploy('https://example.com')
    useCanvasStore.getState().dismissDeployResult()
    const state = useCanvasStore.getState()
    expect(state.deployResultVisible).toBe(false)
    expect(state.deployStatus).toBe('success')
    expect(state.deployedUrl).toBe('https://example.com')
  })

  it('should fail deploy', () => {
    useCanvasStore.getState().startDeploy()
    useCanvasStore.getState().failDeploy()
    const state = useCanvasStore.getState()
    expect(state.isDeploying).toBe(false)
    expect(state.deployStatus).toBe('failed')
  })

  it('should cancel deploy', () => {
    useCanvasStore.getState().startDeploy()
    useCanvasStore.getState().cancelDeploy()
    const state = useCanvasStore.getState()
    expect(state.isDeploying).toBe(false)
    expect(state.deployStatus).toBe('cancelled')
  })

  it('should reset deploy state', () => {
    useCanvasStore.getState().startDeploy()
    useCanvasStore.getState().appendDeployLog('log')
    useCanvasStore.getState().finishDeploy('https://example.com')
    useCanvasStore.getState().resetDeploy()
    const state = useCanvasStore.getState()
    expect(state.isDeploying).toBe(false)
    expect(state.deployStatus).toBe('idle')
    expect(state.deployLogs).toEqual([])
    expect(state.deployedUrl).toBe('')
    expect(state.deployResultVisible).toBe(false)
  })

  // ---------- Task management ----------

  it('should move task to new status', () => {
    useCanvasStore.getState().moveTask(1, 'doing')
    const task = useCanvasStore.getState().tasks.find(t => t.id === 1)
    expect(task.status).toBe('doing')
  })

  it('should add a new task', () => {
    const beforeCount = useCanvasStore.getState().tasks.length
    useCanvasStore.getState().addTask({ title: 'New Task', assignee: 'agent_pm', status: 'todo' })
    const tasks = useCanvasStore.getState().tasks
    expect(tasks.length).toBe(beforeCount + 1)
    expect(tasks[tasks.length - 1].title).toBe('New Task')
  })

  it('should update tasks by agent assignee', () => {
    useCanvasStore.getState().updateTaskByAgent('agent_frontend', 'doing')
    const frontendTask = useCanvasStore.getState().tasks.find(t => t.assignee === 'agent_frontend')
    expect(frontendTask.status).toBe('doing')
    // Other tasks should remain unchanged
    const pmTask = useCanvasStore.getState().tasks.find(t => t.assignee === 'agent_designer')
    expect(pmTask.status).toBe('todo')
  })

  // ---------- DAG node status ----------

  it('should set node status', () => {
    useCanvasStore.getState().setNodeStatus('agent_pm', 'running')
    const node = useCanvasStore.getState().dagNodes.find(n => n.id === 'agent_pm')
    expect(node.status).toBe('running')
  })

  it('should not affect other nodes when setting one node status', () => {
    useCanvasStore.getState().setNodeStatus('agent_pm', 'running')
    const userNode = useCanvasStore.getState().dagNodes.find(n => n.id === 'user')
    expect(userNode.status).toBe('idle')
  })
})

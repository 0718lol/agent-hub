import { expect } from '@playwright/test'

const conversation = {
  id: 'conv_pm',
  type: 'single',
  name: 'PM 小助手',
  agent_id: 'agent_pm',
  preview: '需求分析与任务拆解',
  created_at: '2026-07-15T08:00:00Z',
}

const previousDeployment = {
  id: 'job-previous',
  conversation_id: 'conv_pm',
  target: 'api',
  status: 'success',
  lifecycle: 'superseded',
  provider: 'docker-runtime',
  result_type: 'site',
  url: '/published/job-previous/',
  log: '上一版本发布成功',
  created_at: '2026-07-15T08:10:00Z',
}

const currentDeployment = {
  ...previousDeployment,
  id: 'job-current',
  lifecycle: 'active',
  url: '/published/job-current/',
  log: 'API 服务发布成功',
  created_at: '2026-07-15T08:20:00Z',
  stage: 'complete',
  progress: 100,
  log_entries: [
    { timestamp: '2026-07-15T08:20:00Z', stage: 'queued', level: 'info', message: '任务已进入持久化队列', progress: 5 },
    { timestamp: '2026-07-15T08:20:01Z', stage: 'build', level: 'info', message: 'API 镜像构建完成', progress: 62 },
    { timestamp: '2026-07-15T08:20:02Z', stage: 'complete', level: 'success', message: '发布成功', progress: 100 },
  ],
}

const runningDeployment = {
  ...currentDeployment,
  status: 'running',
  lifecycle: 'active',
  url: '',
  log: '正在隔离构建 API 容器镜像',
  stage: 'build',
  progress: 45,
  log_entries: currentDeployment.log_entries.slice(0, 2),
}

const cancelledDeployment = {
  ...runningDeployment,
  status: 'cancelled',
  log: '构建已被用户取消',
  cancel_requested: false,
  log_entries: [
    ...runningDeployment.log_entries,
    { timestamp: '2026-07-15T08:20:03Z', stage: 'build', level: 'warning', message: '构建已被用户取消', progress: 45 },
  ],
}

const failedDeployment = {
  ...previousDeployment,
  id: 'job-failed',
  target: 'web',
  status: 'failed',
  lifecycle: 'active',
  provider: 'artifact',
  url: '',
  log: '依赖安装失败',
  created_at: '2026-07-15T08:05:00Z',
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

export async function installMockBackend(page, { holdDeployment = false } = {}) {
  const state = { deployed: false, cancelRequested: false, requests: [] }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    state.requests.push({ method, path, body: request.postDataJSON() || null })

    if (path === '/api/auth/status') {
      return json(route, {
        auth_required: true,
        authenticated: true,
        user: { id: 'usr_e2e', tenant_id: 'tn_e2e', username: 'E2E User', is_admin: false },
      })
    }
    if (path === '/api/conversations') return json(route, [conversation])
    if (path === '/api/conversations/conv_pm/messages') return json(route, [])
    if (path === '/api/agents/custom') return json(route, [])
    if (path === '/api/health') return json(route, { status: 'ok', agents: ['agent_pm'] })

    if (path === '/api/deployments' && method === 'GET') {
      const latest = state.cancelRequested
        ? cancelledDeployment
        : holdDeployment && state.deployed
          ? runningDeployment
          : currentDeployment
      return json(route, { deployments: state.deployed ? [latest, previousDeployment, failedDeployment] : [previousDeployment, failedDeployment] })
    }
    if (path === '/api/deploy/conv_pm' && method === 'POST') {
      state.deployed = true
      return json(route, { job_id: currentDeployment.id, status: 'queued' }, 202)
    }
    if (path === `/api/deployments/${currentDeployment.id}` && method === 'GET') {
      if (state.cancelRequested) return json(route, cancelledDeployment)
      return json(route, holdDeployment ? runningDeployment : currentDeployment)
    }
    if (path === `/api/deployments/${currentDeployment.id}/cancel` && method === 'POST') {
      state.cancelRequested = true
      return json(route, { job_id: currentDeployment.id, status: 'cancellation_requested' })
    }
    if (path === `/api/deployments/${previousDeployment.id}/rollback` && method === 'POST') {
      return json(route, { job_id: 'job-rollback', status: 'queued' }, 202)
    }

    return json(route, { detail: `Unhandled E2E route: ${method} ${path}` }, 501)
  })

  return state
}

export async function installMockWebSocket(page) {
  await page.addInitScript(() => {
    const firstPreview = '<!doctype html><html><body><h1>团队待办</h1><button>添加任务</button></body></html>'
    const revisedPreview = '<!doctype html><html><body><h1>团队任务看板</h1><button>新增任务</button><p>支持优先级筛选</p></body></html>'

    class AgentHubMockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      constructor(url) {
        this.url = url
        this.readyState = AgentHubMockWebSocket.CONNECTING
        this.sent = []
        window.setTimeout(() => {
          this.readyState = AgentHubMockWebSocket.OPEN
          this.onopen?.({ type: 'open' })
        }, 0)
      }

      send(raw) {
        const message = JSON.parse(raw)
        this.sent.push(message)
        window.__agentHubE2E.sent.push(message)
        if (message.type !== 'message') return

        const revision = ++window.__agentHubE2E.revision
        const html = revision === 1 ? firstPreview : revisedPreview
        const reply = revision === 1
          ? '第一版工具已经生成，可以在右侧预览。'
          : '已经增加优先级筛选并更新预览。'

        window.setTimeout(() => {
          this.emit({ type: 'generating', conversation_id: message.conversation_id, is_generating: true })
          this.emit({ type: 'preview', conversation_id: message.conversation_id, html })
          this.emit({
            type: 'message',
            conversation_id: message.conversation_id,
            sender: 'agent_pm',
            content: { text: reply },
            stream: false,
          })
          this.emit({ type: 'generating', conversation_id: message.conversation_id, is_generating: false })
        }, 20)
      }

      emit(data) {
        this.onmessage?.({ data: JSON.stringify(data) })
      }

      close() {
        this.readyState = AgentHubMockWebSocket.CLOSED
        this.onclose?.({ code: 1000 })
      }
    }

    window.__agentHubE2E = { revision: 0, sent: [] }
    window.WebSocket = AgentHubMockWebSocket
  })
}

export async function expectApiRequest(state, method, path) {
  await expect.poll(() => state.requests.some((request) => request.method === method && request.path === path)).toBe(true)
}

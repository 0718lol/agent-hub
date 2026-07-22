import { expect, test } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

test.skip(!process.env.REAL_BACKEND, 'Set REAL_BACKEND=1 to exercise the real FastAPI and Redis services')

test('真实后端支持会话、上传与部署可用性反馈', async ({ page }) => {
  const backendBase = (process.env.REAL_BACKEND_URL || '').replace(/\/$/, '')
  const apiUrl = (path) => `${backendBase}${path}`

  await page.goto('/')
  await expect(page.locator('#root')).not.toBeEmpty()

  await page.getByLabel('输入消息').fill('谢谢你的帮助')
  await page.getByLabel('发送消息').click()
  await expect(page.getByText('不客气！有新的需求随时告诉我，我会帮你拆解和协调资源。', { exact: true })).toBeVisible({ timeout: 20_000 })

  const conversations = await page.request.get(apiUrl('/api/conversations'))
  expect(conversations.ok()).toBeTruthy()
  const rows = await conversations.json()
  expect(rows.length).toBeGreaterThan(0)

  const session = (await page.context().cookies()).find((cookie) => cookie.name === 'agenthub_session')
  expect(session).toBeTruthy()
  const userId = session.value.split('.')[1]
  const conversationId = 'conv_pm'
  const workspace = path.resolve(
    process.cwd(),
    '..',
    'agenthub_export',
    `tenant__${userId}__conv__${conversationId}`,
  )
  await mkdir(workspace, { recursive: true })
  await writeFile(
    path.join(workspace, 'index.html'),
    '<!doctype html><html><body><h1>AgentHub E2E</h1></body></html>',
    'utf8',
  )

  const upload = await page.request.post(apiUrl('/api/upload'), {
    multipart: {
      file: {
        name: 'e2e.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('real backend upload'),
      },
    },
  })
  expect(upload.status()).toBe(200)
  const uploaded = await upload.json()

  const download = await page.request.get(apiUrl(uploaded.url))
  expect(download.status()).toBe(200)
  expect(await download.text()).toBe('real backend upload')

  const deploy = await page.request.post(apiUrl(`/api/deploy/${conversationId}`), {
    data: { target: 'web' },
  })
  expect(deploy.status()).toBe(200)
  const queued = await deploy.json()

  await expect.poll(async () => {
    const status = await page.request.get(apiUrl(`/api/deployments/${queued.job_id}`))
    if (!status.ok()) return `http-${status.status()}`
    return (await status.json()).status
  }, { timeout: 30_000 }).toBe('success')

  const status = await page.request.get(apiUrl(`/api/deployments/${queued.job_id}`))
  const completed = await status.json()
  expect(completed.url).toMatch(/^\/uploads\//)
  const artifact = await page.request.get(apiUrl(completed.url))
  expect(artifact.status()).toBe(200)
})

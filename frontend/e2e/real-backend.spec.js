import { expect, test } from '@playwright/test'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

test.skip(!process.env.REAL_BACKEND, 'Set REAL_BACKEND=1 to exercise the real FastAPI and Redis services')

test('真实后端支持会话、上传、部署排队与取消', async ({ page }) => {
  const registration = await page.request.post('/api/auth/register', {
    data: {
      username: `ci_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      password: `E2e-${crypto.randomUUID()}`,
    },
  })
  expect(registration.status()).toBe(201)
  const { user } = await registration.json()

  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('#root')).not.toBeEmpty()

  const conversations = await page.request.get('/api/conversations')
  expect(conversations.ok()).toBeTruthy()
  const rows = await conversations.json()
  expect(rows.length).toBeGreaterThan(0)

  const upload = await page.request.post('/api/upload', {
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

  const download = await page.request.get(uploaded.url)
  expect(download.status()).toBe(200)
  expect(await download.text()).toBe('real backend upload')

  const health = await page.request.get('/api/health')
  expect(health.ok()).toBeTruthy()
  const healthData = await health.json()
  const queueReady = healthData.capabilities?.deployment_queue === true

  const deployUrl = `/api/deploy/${rows[0].id}`
  const deployOptions = { data: { target: 'web' } }
  const emptyDeploy = await page.request.post(deployUrl, deployOptions)
  expect(emptyDeploy.status()).toBe(422)
  expect((await emptyDeploy.json()).detail).toContain('No generated project')

  // The local backend freezes the generated project before checking the queue.
  const exportRoot = fileURLToPath(new URL('../../agenthub_export/', import.meta.url))
  const workspace = join(exportRoot, `tenant__${user.tenant_id}__conv__${rows[0].id}`)
  await mkdir(exportRoot, { recursive: true })
  await mkdir(workspace)
  let deploy
  try {
    await writeFile(join(workspace, 'index.html'), '<h1>Deployment smoke test</h1>')
    deploy = await page.request.post(deployUrl, deployOptions)
  } finally {
    await rm(workspace, { recursive: true, force: true })
  }
  if (!queueReady) {
    expect(deploy.status()).toBe(503)
    expect((await deploy.json()).detail).toMatch(/Redis|Worker/)
    return
  }
  expect(deploy.status()).toBe(200)
  const queued = await deploy.json()
  expect(queued.snapshot_id).toMatch(/^[a-f0-9]{32}$/)
  expect(queued.input_hash).toMatch(/^[a-f0-9]{64}$/)

  const status = await page.request.get(`/api/deployments/${queued.job_id}`)
  expect(status.status()).toBe(200)
  expect((await status.json()).status).toBe('queued')

  const cancel = await page.request.post(`/api/deployments/${queued.job_id}/cancel`)
  expect(cancel.status()).toBe(200)
  expect((await cancel.json()).status).toBe('cancellation_requested')
})

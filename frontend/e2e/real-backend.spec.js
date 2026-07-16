import { expect, test } from '@playwright/test'

test.skip(!process.env.REAL_BACKEND, 'Set REAL_BACKEND=1 to exercise the real FastAPI and Redis services')

test('真实后端支持会话、上传、部署排队与取消', async ({ page }) => {
  await page.goto('/')
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

  const deploy = await page.request.post(`/api/deploy/${rows[0].id}`, {
    data: { target: 'web' },
  })
  expect(deploy.status()).toBe(200)
  const queued = await deploy.json()

  const status = await page.request.get(`/api/deployments/${queued.job_id}`)
  expect(status.status()).toBe(200)
  expect((await status.json()).status).toBe('queued')

  const cancel = await page.request.post(`/api/deployments/${queued.job_id}/cancel`)
  expect(cancel.status()).toBe(200)
  expect((await cancel.json()).status).toBe('cancellation_requested')
})

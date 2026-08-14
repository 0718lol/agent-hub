import { expect, test } from '@playwright/test'

test.skip(!process.env.REAL_ACCOUNT_PASSWORD, 'Set REAL_ACCOUNT_PASSWORD to test a real local account')

test('账户登录、管理员恢复区、退出和稳定租户', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'AgentHub' })).toBeVisible()
  await expect(page.getByRole('button', { name: '注册' })).toBeVisible()
  await expect(page.getByText('找回密码')).toHaveCount(0)

  await page.getByLabel('用户名').fill('Wac')
  await page.getByLabel('密码').fill(process.env.REAL_ACCOUNT_PASSWORD)
  await page.getByRole('button', { name: '进入 AgentHub' }).click()

  await expect(page.getByText('Wac', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '退出' })).toBeVisible()

  const firstResponse = await page.request.get('/api/conversations')
  expect(firstResponse.ok()).toBeTruthy()
  const firstIds = (await firstResponse.json()).map((conversation) => conversation.id)

  await page.getByRole('button', { name: '设置' }).click()
  await page.getByRole('button', { name: /安全/ }).click()
  await expect(page.getByText('管理员账户')).toBeVisible()
  await expect(page.getByText('旧租户恢复区')).toBeVisible()
  await page.getByRole('button', { name: '×' }).click()

  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('button', { name: '进入 AgentHub' })).toBeVisible()
  expect((await page.request.get('/api/conversations')).status()).toBe(401)

  await page.getByLabel('用户名').fill('Wac')
  await page.getByLabel('密码').fill(process.env.REAL_ACCOUNT_PASSWORD)
  await page.getByRole('button', { name: '进入 AgentHub' }).click()
  await expect(page.getByRole('button', { name: '退出' })).toBeVisible()

  const secondResponse = await page.request.get('/api/conversations')
  expect(secondResponse.ok()).toBeTruthy()
  const secondIds = (await secondResponse.json()).map((conversation) => conversation.id)
  expect(secondIds).toEqual(firstIds)

})

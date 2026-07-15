import { expect, test } from '@playwright/test'
import { expectApiRequest, installMockBackend, installMockWebSocket } from './mockBackend'

test('用户可以生成、修改、预览、发布并回滚工具软件', async ({ page }) => {
  await installMockWebSocket(page)
  const backend = await installMockBackend(page)

  await page.goto('/')
  await expect(page.getByText('PM 小助手', { exact: true }).first()).toBeVisible()

  const input = page.getByLabel('输入消息')
  await input.fill('生成一个团队待办工具')
  await page.getByRole('button', { name: '发送消息' }).click()
  await expect(page.getByText('第一版工具已经生成，可以在右侧预览。')).toBeVisible()

  await page.getByText('展开侧边栏', { exact: true }).locator('..').click()
  const sidePanel = page.locator('.slide-panel.open')
  await expect(sidePanel).toBeVisible()
  await sidePanel.getByRole('button', { name: '预览' }).click()
  await expect(sidePanel.frameLocator('iframe[title="Preview"]').locator('h1')).toHaveText('团队待办')

  await input.fill('增加优先级筛选，并把添加按钮改成新增任务')
  await page.getByRole('button', { name: '发送消息' }).click()
  await expect(page.getByText('已经增加优先级筛选并更新预览。')).toBeVisible()
  const preview = sidePanel.frameLocator('iframe[title="Preview"]')
  await expect(preview.locator('h1')).toHaveText('团队任务看板')
  await expect(preview.getByRole('button', { name: '新增任务' })).toBeVisible()
  await expect(preview.getByText('支持优先级筛选')).toBeVisible()

  await sidePanel.getByRole('button', { name: '部署' }).click()
  await expect(sidePanel.getByText('构建与发布流水线')).toBeVisible()
  await expect(sidePanel.getByTitle('下载失败日志')).toHaveAttribute('href', '/api/deployments/job-failed/logs')
  await sidePanel.getByRole('group', { name: '发布目标' }).getByRole('button', { name: 'API', exact: true }).click()
  await sidePanel.getByRole('button', { name: '启动流水线' }).click()

  await expectApiRequest(backend, 'POST', '/api/deploy/conv_pm')
  await expect(sidePanel.getByText('API 发布成功')).toBeVisible()
  await expect(sidePanel.getByText('/published/job-current/')).toBeVisible()
  await expect(sidePanel.getByRole('progressbar', { name: '部署进度' })).toHaveAttribute('aria-valuenow', '100')

  await sidePanel.getByTitle('回滚到此版本').last().click()
  await expectApiRequest(backend, 'POST', '/api/deployments/job-previous/rollback')
  await expect(sidePanel.getByText('操作已进入队列')).toBeVisible()
})

test('用户可以取消正在运行的构建任务', async ({ page }) => {
  await installMockWebSocket(page)
  const backend = await installMockBackend(page, { holdDeployment: true })

  await page.goto('/')
  await page.getByText('展开侧边栏', { exact: true }).locator('..').click()
  const sidePanel = page.locator('.slide-panel.open')
  await sidePanel.getByRole('button', { name: '部署' }).click()
  await sidePanel.getByRole('group', { name: '发布目标' }).getByRole('button', { name: 'API', exact: true }).click()
  await sidePanel.getByRole('button', { name: '启动流水线' }).click()
  await expect(sidePanel.getByRole('button', { name: '取消构建' })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await sidePanel.getByRole('button', { name: '取消构建' }).click()

  await expectApiRequest(backend, 'POST', '/api/deployments/job-current/cancel')
  await expect(sidePanel.getByText('构建已被用户取消')).toBeVisible({ timeout: 5_000 })
  await expect(sidePanel.getByRole('button', { name: '启动流水线' })).toBeVisible()
})

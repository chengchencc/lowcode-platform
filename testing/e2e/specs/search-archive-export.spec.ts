import { readFile } from 'node:fs/promises'

import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import {
  approveViaApi,
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  submitFor,
} from '../fixtures/factories'
import { buttonName } from '../fixtures/ui'

async function setup() {
  const users = await seedUsers()
  const form = await createFormAndPublish('E2E 检索归档表单')
  const flow = await createFlowAndPublish(
    form.id,
    'E2E 检索归档流程',
    sequentialDefinition([{ id: 'a1', name: '初审', userId: users.lisi.id }]),
  )
  const approved = await submitFor('zhangsan', flow.id, {
    reason: uniqueReason('E2E 已通过'),
    amount: 120,
  })
  await approveViaApi('lisi', approved.id, '通过')
  const running = await submitFor('zhangsan', flow.id, {
    reason: uniqueReason('E2E 运行中'),
    amount: 80,
  })
  return { approved, running }
}

async function readDownload(page: import('@playwright/test').Page, trigger: () => Promise<void>): Promise<string> {
  const [download] = await Promise.all([page.waitForEvent('download'), trigger()])
  const path = await download.path()
  if (!path) throw new Error('浏览器没有给出下载文件路径')
  return readFile(path, 'utf8')
}

test.describe('@p0 检索、归档与导出', () => {
  test('@p0 归档台账只列办结实例，可按单号检索', async ({ browser }) => {
    const { approved, running } = await setup()
    const admin = await openAs(browser, 'admin')
    try {
      await admin.page.goto('/admin/archive')
      const search = admin.page.getByPlaceholder('标题 / 实例单号')

      await search.fill(approved.code)
      await admin.page.getByRole('button', { name: buttonName('查询') }).click()
      await expect(admin.page.locator('tbody tr').filter({ hasText: approved.code })).toBeVisible()

      await search.fill(running.code)
      await admin.page.getByRole('button', { name: buttonName('查询') }).click()
      await expect(admin.page.locator('tbody tr').filter({ hasText: running.code })).toHaveCount(0)
    } finally {
      await admin.context.close()
    }
  })

  test('@p0 实例管理同时列出运行中与办结，且不提供导出', async ({ browser }) => {
    const { approved, running } = await setup()
    const admin = await openAs(browser, 'admin')
    try {
      await admin.page.goto('/admin/instances')
      const search = admin.page.getByPlaceholder('标题 / 实例单号')

      await search.fill(running.code)
      await admin.page.getByRole('button', { name: buttonName('查询') }).click()
      await expect(admin.page.locator('tbody tr').filter({ hasText: running.code })).toBeVisible()

      await search.fill(approved.code)
      await admin.page.getByRole('button', { name: buttonName('查询') }).click()
      await expect(admin.page.locator('tbody tr').filter({ hasText: approved.code })).toBeVisible()

      await expect(admin.page.getByRole('button', { name: '导出 CSV' })).toHaveCount(0)
    } finally {
      await admin.context.close()
    }
  })

  test('@p0 归档 CSV 按当前筛选导出且包含动态列', async ({ browser }) => {
    const { approved } = await setup()
    const admin = await openAs(browser, 'admin')
    try {
      await admin.page.goto('/admin/archive')
      const search = admin.page.getByPlaceholder('标题 / 实例单号')
      await search.fill(approved.code)
      await admin.page.getByRole('button', { name: buttonName('查询') }).click()
      await expect(admin.page.locator('tbody tr').filter({ hasText: approved.code })).toBeVisible()

      const csv = await readDownload(admin.page, () =>
        admin.page.getByRole('button', { name: '导出 CSV' }).click(),
      )
      expect(csv).toContain(approved.code)
      expect(csv).toContain(approved.title)
      expect(csv).toContain('事由')
      expect(csv).not.toContain('E2E 运行中')
    } finally {
      await admin.context.close()
    }
  })

  test('@p0 我发起的可检索，详情可导出', async ({ browser }) => {
    const { approved } = await setup()
    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto('/workbench/mine')
      const search = initiator.page.getByPlaceholder('标题或实例单号')
      await search.fill(approved.code)
      await search.press('Enter')
      const row = initiator.page.locator('tbody tr').filter({ hasText: approved.code })
      await expect(row).toBeVisible()

      await initiator.page.goto(`/instance/${approved.id}`)
      await expect(initiator.page.getByText('已通过').first()).toBeVisible()
      const csv = await readDownload(initiator.page, () =>
        initiator.page.getByRole('button', { name: buttonName('导出') }).click(),
      )
      expect(csv).toContain(approved.code)
      expect(csv).toContain(approved.title)
      expect(csv).toContain('事由')
    } finally {
      await initiator.context.close()
    }
  })
})

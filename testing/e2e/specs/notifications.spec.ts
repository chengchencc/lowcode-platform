import { expect, test } from '@playwright/test'

import { apiAs, openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  submitFor,
} from '../fixtures/factories'

async function unreadCount(role: 'lisi' | 'zhangsan'): Promise<number> {
  const api = await apiAs(role)
  try {
    const response = await api.get('notifications/unread-count')
    expect(response.ok()).toBeTruthy()
    return ((await response.json()) as { count: number }).count
  } finally {
    await api.dispose()
  }
}

test.describe('@p0 消息中心', () => {
  test('@p0 新待办生成通知，可单条与全部标记已读', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 通知表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 通知流程',
      sequentialDefinition([{ id: 'a1', name: '初审', userId: users.lisi.id }]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 通知'),
      amount: 100,
    })

    const before = await unreadCount('lisi')
    expect(before).toBeGreaterThan(0)

    const approver = await openAs(browser, 'lisi')
    try {
      await approver.page.goto('/messages')
      const row = approver.page.locator('tbody tr').filter({ hasText: instance.title })
      await expect(row).toBeVisible()
      await expect(row.getByText('未读')).toBeVisible()

      await row.getByRole('button', { name: '已读' }).click()
      await expect(row.getByText('未读')).toHaveCount(0)
      expect(await unreadCount('lisi')).toBe(before - 1)

      await approver.page.getByRole('button', { name: '全部已读' }).click()
      await expect(approver.page.getByText(/已标记 \d+ 条为已读/)).toBeVisible()
      expect(await unreadCount('lisi')).toBe(0)
    } finally {
      await approver.context.close()
    }
  })

  test('@p0 首页待办角标在 10 秒内感知新任务', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 轮询表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 轮询流程',
      sequentialDefinition([{ id: 'a1', name: '初审', userId: users.lisi.id }]),
    )

    const api = await apiAs('lisi')
    let before = 0
    try {
      const summary = await api.get('tasks/summary')
      expect(summary.ok()).toBeTruthy()
      before = ((await summary.json()) as { todo: number }).todo
    } finally {
      await api.dispose()
    }

    const approver = await openAs(browser, 'lisi')
    try {
      await approver.page.goto('/dashboard')
      const tile = approver.page
        .locator('.ant-statistic')
        .filter({ hasText: '待办' })
        .first()
      await expect(tile).toContainText(String(before))

      await submitFor('zhangsan', flow.id, {
        reason: uniqueReason('E2E 轮询'),
        amount: 100,
      })

      // 布局每 10s 轮询一次；给 15s 余量
      await expect(tile).toContainText(String(before + 1), { timeout: 15_000 })
    } finally {
      await approver.context.close()
    }
  })
})

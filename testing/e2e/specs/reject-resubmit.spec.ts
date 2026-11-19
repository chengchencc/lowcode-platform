import { expect, test, type Page } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, submitLeaveAsZhangsan, uniqueReason } from '../fixtures/data'

async function openTodoByCode(page: Page, code: string, instanceId: number): Promise<void> {
  await page.goto('/workbench/todo')
  const search = page.getByPlaceholder('标题或实例单号')
  await search.fill(code)
  await search.press('Enter')

  const row = page.locator('tbody tr').filter({ hasText: code })
  await expect(row).toBeVisible()
  await row.locator('td').first().locator('a').click()
  await expect(page).toHaveURL(new RegExp(`/instance/${instanceId}`))
}

test.describe('@p0 驳回与重提', () => {
  test('@p0 审批人驳回后，发起人修改并重提，轮次 +1', async ({ browser }) => {
    const reason = uniqueReason('E2E 驳回')
    const instance = await submitLeaveAsZhangsan(reason)

    // 1. 李四驳回，必须写意见
    const approver = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(approver.page, instance.code, instance.id)
      // antd 会在两个汉字的按钮里插空格，可访问名是「驳 回」
      await approver.page.getByRole('button', { name: /驳\s*回/ }).click()
      const rejection = uniqueReason('驳回意见')
      await approver.page.getByPlaceholder('必填', { exact: true }).fill(rejection)
      await approver.page.getByRole('button', { name: '确认驳回' }).click()

      await expect(approver.page.getByText('已驳回').first()).toBeVisible()

      const rejected = await renderAs('zhangsan', instance.id)
      expect(rejected.instance.status).toBe('REJECTED')
      expect(
        rejected.actions.some((item) => item.action === 'REJECT' && item.opinion === rejection),
      ).toBeTruthy()
    } finally {
      await approver.context.close()
    }

    // 2. 张三看到驳回意见，改事由后重新提交
    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto(`/instance/${instance.id}`)
      await expect(initiator.page.getByText(/被驳回：/)).toBeVisible()
      await initiator.page.getByRole('button', { name: '修改并重新提交' }).click()

      const updated = uniqueReason('E2E 重提')
      await initiator.page.getByPlaceholder('请输入事由').fill(updated)
      await initiator.page.getByRole('button', { name: '确认重新提交' }).click()

      await expect(initiator.page.getByText('已重新提交，流程从头开始走')).toBeVisible()
      await expect(initiator.page.getByText('第 2 轮').first()).toBeVisible()
      await expect(initiator.page.getByText('审批中').first()).toBeVisible()

      const resubmitted = await renderAs('zhangsan', instance.id)
      expect(resubmitted.instance.status).toBe('RUNNING')
      expect(resubmitted.instance.round).toBe(2)
      expect(resubmitted.values.reason).toBe(updated)
      // 上一轮的驳回记录保留，便于追溯
      expect(resubmitted.actions.some((item) => item.action === 'REJECT')).toBeTruthy()
    } finally {
      await initiator.context.close()
    }
  })
})

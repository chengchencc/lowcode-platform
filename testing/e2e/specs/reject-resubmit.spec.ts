import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, submitLeaveAsZhangsan, uniqueReason } from '../fixtures/data'
import { openTodoByCode, rejectViaUi } from '../fixtures/ui'

test.describe('@p0 驳回与重提', () => {
  test('@p0 审批人驳回后，发起人修改并重提，轮次 +1', async ({ browser }) => {
    const reason = uniqueReason('E2E 驳回')
    const instance = await submitLeaveAsZhangsan(reason)

    // 1. 李四驳回，必须写意见
    const approver = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(approver.page, instance.code, instance.id)
      const rejection = uniqueReason('驳回意见')
      await rejectViaUi(approver.page, rejection)

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

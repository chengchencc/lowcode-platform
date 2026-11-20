import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  submitFor,
} from '../fixtures/factories'
import { approveViaUi, openTodoByCode } from '../fixtures/ui'

test.describe('@p0 处理历史与快照回放', () => {
  test('@p0 时间线可展开意见并回放当时快照', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 快照表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 快照流程',
      sequentialDefinition([
        { id: 'a1', name: '初审', userId: users.lisi.id },
        { id: 'a2', name: '复核', userId: users.wangwu.id },
      ]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 快照'),
      amount: 100,
    })

    const first = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(first.page, instance.code, instance.id)
      await approveViaUi(first.page, '初审意见-快照')
    } finally {
      await first.context.close()
    }

    const second = await openAs(browser, 'wangwu')
    try {
      await openTodoByCode(second.page, instance.code, instance.id)
      await approveViaUi(second.page, '复核意见-快照')
    } finally {
      await second.context.close()
    }

    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto(`/instance/${instance.id}`)
      await expect(initiator.page.getByText('已通过').first()).toBeVisible()

      // 处理历史默认展开，直接进入当时快照
      await expect(initiator.page.getByText(/查看当时的表单快照/).first()).toBeVisible()
      await initiator.page.getByText(/查看当时的表单快照/).first().click()

      await expect(initiator.page.getByText('正在查看历史快照')).toBeVisible()
      await expect(initiator.page.getByText(/快照 #\d+/).first()).toBeVisible()
      await expect(initiator.page.getByText('退出', { exact: true })).toBeVisible()

      await initiator.page.getByText('退出', { exact: true }).click()
      await expect(initiator.page.getByText('正在查看历史快照')).toHaveCount(0)
    } finally {
      await initiator.context.close()
    }
  })
})

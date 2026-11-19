import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'
import {
  conditionDefinition,
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  submitFor,
  todoInstanceIds,
} from '../fixtures/factories'
import { approveViaUi, openTodoByCode } from '../fixtures/ui'

const THRESHOLD = 1000

async function setup() {
  const users = await seedUsers()
  const form = await createFormAndPublish('E2E 条件表单')
  const flow = await createFlowAndPublish(
    form.id,
    'E2E 条件流程',
    conditionDefinition(THRESHOLD, users.lisi.id, users.admin.id),
  )
  return { users, flow }
}

test.describe('@p0 条件分支', () => {
  test('@p0 未命中分支：初审通过后直接结束', async ({ browser }) => {
    const { flow } = await setup()
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 条件-小额'),
      amount: THRESHOLD - 100,
    })

    const approver = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(approver.page, instance.code, instance.id)
      await approveViaUi(approver.page, '小额同意')
    } finally {
      await approver.context.close()
    }

    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('APPROVED')
    expect(await todoInstanceIds('admin')).not.toContain(instance.id)
  })

  test('@p0 命中分支：初审后进入大额复核，复核通过才结束', async ({ browser }) => {
    const { flow } = await setup()
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 条件-大额'),
      amount: THRESHOLD + 500,
    })

    const first = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(first.page, instance.code, instance.id)
      await approveViaUi(first.page, '初审同意')
      await expect(first.page.getByText('大额复核').first()).toBeVisible()
      await expect(first.page.getByText('审批中').first()).toBeVisible()
    } finally {
      await first.context.close()
    }

    const running = await renderAs('zhangsan', instance.id)
    expect(running.instance.status).toBe('RUNNING')
    expect(await todoInstanceIds('admin')).toContain(instance.id)

    const second = await openAs(browser, 'admin')
    try {
      await openTodoByCode(second.page, instance.code, instance.id)
      await approveViaUi(second.page, '大额复核通过')
    } finally {
      await second.context.close()
    }

    const approved = await renderAs('zhangsan', instance.id)
    expect(approved.instance.status).toBe('APPROVED')
  })
})

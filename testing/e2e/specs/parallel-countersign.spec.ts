import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  parallelDefinition,
  seedUsers,
  submitFor,
  todoInstanceIds,
} from '../fixtures/factories'
import { approveViaUi, openTodoByCode, rejectViaUi } from '../fixtures/ui'

test.describe('@p0 会签与或签', () => {
  test('@p0 会签：两人分别同意后实例才通过', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 会签表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 会签流程',
      parallelDefinition('all', [
        { id: 'm1', name: '会签成员1', userId: users.lisi.id },
        { id: 'm2', name: '会签成员2', userId: users.wangwu.id },
      ]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 会签'),
      amount: 100,
    })

    const first = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(first.page, instance.code, instance.id)
      await approveViaUi(first.page, '会签同意')
      const stillRunning = await renderAs('zhangsan', instance.id)
      expect(stillRunning.instance.status).toBe('RUNNING')
    } finally {
      await first.context.close()
    }

    const second = await openAs(browser, 'wangwu')
    try {
      await openTodoByCode(second.page, instance.code, instance.id)
      await approveViaUi(second.page, '会签同意')
    } finally {
      await second.context.close()
    }

    const approved = await renderAs('zhangsan', instance.id)
    expect(approved.instance.status).toBe('APPROVED')
  })

  test('@p0 或签：一人同意后其余待办取消', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 或签表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 或签流程',
      parallelDefinition('any', [
        { id: 'm1', name: '或签成员1', userId: users.lisi.id },
        { id: 'm2', name: '或签成员2', userId: users.wangwu.id },
      ]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 或签'),
      amount: 100,
    })

    const first = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(first.page, instance.code, instance.id)
      await approveViaUi(first.page, '或签通过')
    } finally {
      await first.context.close()
    }

    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('APPROVED')
    expect(await todoInstanceIds('wangwu')).not.toContain(instance.id)

    const second = await openAs(browser, 'wangwu')
    try {
      await second.page.goto('/workbench/todo')
      const search = second.page.getByPlaceholder('标题或实例单号')
      await search.fill(instance.code)
      await search.press('Enter')
      await expect(second.page.locator('tbody tr').filter({ hasText: instance.code })).toHaveCount(0)
    } finally {
      await second.context.close()
    }
  })

  test('@p0 会签：一人驳回则整单驳回，其余待办取消', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 会签驳回表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 会签驳回流程',
      parallelDefinition('all', [
        { id: 'm1', name: '会签成员1', userId: users.lisi.id },
        { id: 'm2', name: '会签成员2', userId: users.wangwu.id },
      ]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 会签驳回'),
      amount: 100,
    })

    const first = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(first.page, instance.code, instance.id)
      await rejectViaUi(first.page, '会签驳回意见')
    } finally {
      await first.context.close()
    }

    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('REJECTED')
    expect(await todoInstanceIds('wangwu')).not.toContain(instance.id)
  })
})

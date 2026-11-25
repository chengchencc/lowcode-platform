import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, submitLeaveAsZhangsan, uniqueReason } from '../fixtures/data'
import {
  approveViaApi,
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  submitFor,
  todoInstanceIds,
} from '../fixtures/factories'
import { approveViaUi, buttonName, openTodoByCode } from '../fixtures/ui'

test.describe('@p0 审批人旅程', () => {
  test('@p0 待办打开实例、填写意见并同意', async ({ browser }) => {
    const reason = uniqueReason('E2E 同意')
    const instance = await submitLeaveAsZhangsan(reason)

    const { context, page } = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(page, instance.code, instance.id)
      await expect(page.getByText('直属上级审批').first()).toBeVisible()

      const opinion = uniqueReason('同意意见')
      await approveViaUi(page, opinion)
      await expect(page.getByText('已通过').first()).toBeVisible()

      const rendered = await renderAs('zhangsan', instance.id)
      expect(rendered.instance.status).toBe('APPROVED')
      expect(
        rendered.actions.some((item) => item.action === 'AGREE' && item.opinion === opinion),
      ).toBeTruthy()
    } finally {
      await context.close()
    }
  })

  test('@p0 已办列表能看到刚处理的实例', async ({ browser }) => {
    const instance = await submitLeaveAsZhangsan(uniqueReason('E2E 已办'))

    const { context, page } = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(page, instance.code, instance.id)
      await approveViaUi(page)

      await page.goto('/workbench/done')
      const search = page.getByPlaceholder('标题或实例单号')
      await search.fill(instance.code)
      await search.press('Enter')
      const row = page.locator('tbody tr').filter({ hasText: instance.code })
      await expect(row).toBeVisible()
      await expect(row.getByText('同意', { exact: true })).toBeVisible()
    } finally {
      await context.close()
    }
  })

  test('@p1 审批人可在下游处理前撤回自己的审批', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish(`E2E 撤回审批表单 ${uniqueReason('')}`)
    const flow = await createFlowAndPublish(
      form.id,
      `E2E 撤回审批流程 ${uniqueReason('')}`,
      sequentialDefinition([
        { id: 'a1', name: '一级审批', userId: users.lisi.id },
        { id: 'a2', name: '二级审批', userId: users.wangwu.id },
      ]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 撤回审批'),
      amount: 100,
    })
    await approveViaApi('lisi', instance.id, '先同意')

    const { context, page } = await openAs(browser, 'lisi')
    try {
      await page.goto(`/instance/${instance.id}`)
      await expect(page.getByText('一级审批').first()).toBeVisible()

      await page.getByRole('button', { name: buttonName('撤回审批') }).click()
      await page.getByRole('dialog').getByRole('button', { name: buttonName('确定') }).click()
      await expect(page.getByText('已撤回审批')).toBeVisible()

      const rendered = await renderAs('lisi', instance.id)
      expect(rendered.actions.some((item) => item.action === 'REVOKE_APPROVAL')).toBeTruthy()
      // 下游王五的待办已经被取消
      expect(await todoInstanceIds('wangwu')).not.toContain(instance.id)
      // 本节点重新派回李四
      await expect(page.getByRole('button', { name: buttonName('同意') })).toBeVisible()
    } finally {
      await context.close()
    }
  })
})

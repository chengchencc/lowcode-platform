import { expect, test } from '@playwright/test'

import { apiAs, openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  submitFor,
  todoInstanceIds,
} from '../fixtures/factories'
import { approveViaUi, buttonName, openTodoByCode } from '../fixtures/ui'

test.describe('@p0 转办与委托', () => {
  test('@p0 待办转办后新处理人收到任务，原处理人保留查看权', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 转办表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 转办流程',
      sequentialDefinition([{ id: 'a1', name: '初审', userId: users.lisi.id }]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 转办'),
      amount: 100,
    })

    const owner = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(owner.page, instance.code, instance.id)
      // 回到列表操作转办，验证的是列表行内入口
      await owner.page.goto('/workbench/todo')
      const search = owner.page.getByPlaceholder('标题或实例单号')
      await search.fill(instance.code)
      await search.press('Enter')
      const row = owner.page.locator('tbody tr').filter({ hasText: instance.code })
      await row.getByRole('button', { name: buttonName('转办') }).click()

      const dialog = owner.page.getByRole('dialog')
      const picker = dialog.getByRole('combobox').first()
      await picker.click()
      await picker.fill('王五')
      await picker.press('Enter')
      await dialog.getByPlaceholder('必填，会写入处理历史').fill('E2E 转办给财务')
      await dialog.getByRole('button', { name: '确认转办' }).click()
      await expect(owner.page.getByText('已转办')).toBeVisible()
    } finally {
      await owner.context.close()
    }

    expect(await todoInstanceIds('lisi')).not.toContain(instance.id)
    expect(await todoInstanceIds('wangwu')).toContain(instance.id)

    // 原处理人不再有待办，但仍可查看这张单（PHASE3 §4.4）
    const origin = await openAs(browser, 'lisi')
    try {
      await origin.page.goto(`/instance/${instance.id}`)
      await expect(origin.page.getByText('审批中').first()).toBeVisible()
      await expect(origin.page.getByText('已转办', { exact: false })).toHaveCount(0)
    } finally {
      await origin.context.close()
    }

    const assignee = await openAs(browser, 'wangwu')
    try {
      await openTodoByCode(assignee.page, instance.code, instance.id)
      await approveViaUi(assignee.page, '转办后同意')
    } finally {
      await assignee.context.close()
    }

    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('APPROVED')
  })

  test('@p0 委托列表显示生效状态并可取消', async ({ browser }) => {
    const users = await seedUsers()
    const api = await apiAs('lisi')
    try {
      // 重试时先清掉上一轮残留的生效委托，避免时段重叠冲突
      const existing = await api.get('delegations')
      expect(existing.ok()).toBeTruthy()
      for (const item of (await existing.json()) as Array<{ id: number; status: string }>) {
        if (item.status === 'ACTIVE') {
          await api.post(`delegations/${item.id}/cancel`)
        }
      }

      const start = new Date(Date.now() - 60 * 60 * 1000).toISOString()
      const end = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
      const created = await api.post('delegations', {
        data: {
          delegatee_id: users.wangwu.id,
          start_at: start,
          end_at: end,
          reason: uniqueReason('E2E 委托'),
          flow_template_ids: [],
        },
      })
      expect(created.ok()).toBeTruthy()
    } finally {
      await api.dispose()
    }

    const view = await openAs(browser, 'lisi')
    try {
      await view.page.goto('/delegations')
      await expect(view.page.getByText('王五').first()).toBeVisible()
      await expect(view.page.getByText('生效中').first()).toBeVisible()

      const row = view.page.locator('tbody tr').filter({ hasText: 'E2E 委托' })
      await row.getByRole('button', { name: buttonName('取消') }).click()
      await view.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(view.page.getByText('已取消').first()).toBeVisible()
      await expect(
        view.page.locator('tbody tr').filter({ hasText: 'E2E 委托' }).getByText('已取消'),
      ).toBeVisible()
    } finally {
      await view.context.close()
    }
  })
})

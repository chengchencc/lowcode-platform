import { expect, test } from '@playwright/test'

import { apiAs, openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'
import {
  approveViaApi,
  createFlowAndPublish,
  createFormAndPublish,
  findAssignment,
  returnDefinition,
  seedUsers,
  sequentialDefinition,
  submitFor,
  todoInstanceIds,
} from '../fixtures/factories'
import { approveViaUi, buttonName, openTodoByCode } from '../fixtures/ui'

async function setupSequential() {
  const users = await seedUsers()
  const form = await createFormAndPublish('E2E 生命周期表单')
  const flow = await createFlowAndPublish(
    form.id,
    'E2E 生命周期流程',
    sequentialDefinition([
      { id: 'a1', name: '初审', userId: users.lisi.id },
      { id: 'a2', name: '复核', userId: users.wangwu.id },
    ]),
  )
  return { users, flow }
}

test.describe('@p0 撤回/终止/退回', () => {
  test('@p0 尚无处理记录时发起人可以撤回', async ({ browser }) => {
    const { flow } = await setupSequential()
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 撤回'),
      amount: 100,
    })

    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto(`/instance/${instance.id}`)
      await initiator.page.getByRole('button', { name: buttonName('撤回') }).click()
      await initiator.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(initiator.page.getByText('已撤回').first()).toBeVisible()
    } finally {
      await initiator.context.close()
    }

    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('WITHDRAWN')
    expect(await todoInstanceIds('lisi')).not.toContain(instance.id)
  })

  test('@p0 已被处理过的实例不再显示撤回入口，服务端仍兜底拒绝', async ({ browser }) => {
    const { flow } = await setupSequential()
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 撤回守卫'),
      amount: 100,
    })
    await approveViaApi('lisi', instance.id, '已处理')

    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto(`/instance/${instance.id}`)
      await expect(initiator.page.getByText('审批中').first()).toBeVisible()
      // 服务端判定 can_withdraw=false：不渲染按钮，而不是渲染后点了才报错
      await expect(
        initiator.page.getByRole('button', { name: buttonName('撤回') }),
      ).toHaveCount(0)
    } finally {
      await initiator.context.close()
    }

    // 直接调接口仍被拒：前端隐藏入口只是 UX，规则由服务端兜底
    const api = await apiAs('zhangsan')
    try {
      const response = await api.post(`instances/${instance.id}/withdraw`, {
        data: { reason: null },
      })
      expect(response.status()).toBe(422)
      expect(await response.text()).toContain('不能撤回')
    } finally {
      await api.dispose()
    }

    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('RUNNING')
  })

  test('@p0 管理员终止后所有待办取消', async ({ browser }) => {
    const { flow } = await setupSequential()
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 终止'),
      amount: 100,
    })

    const admin = await openAs(browser, 'admin')
    try {
      await admin.page.goto(`/instance/${instance.id}`)
      await admin.page.getByRole('button', { name: buttonName('终止') }).click()
      await admin.page
        .getByPlaceholder('必填，会写入审计与通知')
        .fill('E2E 终止原因')
      await admin.page.getByRole('button', { name: '确认终止' }).click()
      await expect(admin.page.getByText('已终止').first()).toBeVisible()
      await expect(admin.page.getByText('终止原因：E2E 终止原因')).toBeVisible()
    } finally {
      await admin.context.close()
    }

    expect(await todoInstanceIds('lisi')).not.toContain(instance.id)
    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('TERMINATED')
  })

  test('@p0 复核节点退回前序节点后重新派单', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 退回表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 退回流程',
      returnDefinition(users.lisi.id, users.wangwu.id),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 退回'),
      amount: 100,
    })

    const first = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(first.page, instance.code, instance.id)
      await approveViaUi(first.page, '初审通过')
    } finally {
      await first.context.close()
    }

    const second = await openAs(browser, 'wangwu')
    try {
      await openTodoByCode(second.page, instance.code, instance.id)
      await second.page.getByRole('button', { name: buttonName('退回') }).click()

      const target = second.page.getByRole('combobox').last()
      await target.click()
      // 下拉是只读搜索框，用键盘选中唯一候选
      await target.press('ArrowDown')
      await target.press('Enter')
      await second.page.getByPlaceholder('选填', { exact: true }).fill('数据有误，请重填')
      await second.page.getByRole('button', { name: '确认退回' }).click()

      await expect(second.page.getByText('已退回')).toBeVisible()
      await expect(second.page.getByText('审批中').first()).toBeVisible()
    } finally {
      await second.context.close()
    }

    const rerouted = await findAssignment('lisi', instance.id)
    expect(rerouted.node_name).toBe('退回目标审批')
    expect(await todoInstanceIds('wangwu')).not.toContain(instance.id)
    const rendered = await renderAs('zhangsan', instance.id)
    expect(rendered.instance.status).toBe('RUNNING')
  })
})

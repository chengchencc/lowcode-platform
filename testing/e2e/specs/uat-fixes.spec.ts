import { expect, test } from '@playwright/test'

import { apiAs, openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  findAssignment,
  seedUsers,
  sequentialDefinition,
  submitFor,
} from '../fixtures/factories'
import { buttonName } from '../fixtures/ui'

async function actAs(role: 'lisi', assignmentId: number, action: 'REJECT' | 'AGREE'): Promise<void> {
  const api = await apiAs(role)
  try {
    const response = await api.post(`tasks/assignments/${assignmentId}/act`, {
      data: {
        action,
        opinion: action === 'REJECT' ? 'UAT 驳回' : '同意',
        attachment_ids: [],
        field_patch: {},
        return_target: null,
      },
    })
    expect(response.ok()).toBeTruthy()
  } finally {
    await api.dispose()
  }
}

test.describe('@p0 UAT 反馈回归', () => {
  test('@p0 单节点流程隐藏退回；驳回/撤回在「我发起的」提供入口', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('UAT 反馈表单')
    const flow = await createFlowAndPublish(
      form.id,
      'UAT 反馈流程',
      sequentialDefinition([{ id: 'a1', name: '审批', userId: users.lisi.id }]),
    )

    const rejectedData = {
      reason: uniqueReason('UAT 驳回'),
      amount: 100,
    }
    const rejected = await submitFor('zhangsan', flow.id, rejectedData)
    const task = await findAssignment('lisi', rejected.id)
    await actAs('lisi', task.assignment_id, 'REJECT')

    const withdrawnData = {
      reason: uniqueReason('UAT 撤回'),
      amount: 80,
    }
    const withdrawn = await submitFor('zhangsan', flow.id, withdrawnData)
    const withdrawApi = await apiAs('zhangsan')
    try {
      const response = await withdrawApi.post(`instances/${withdrawn.id}/withdraw`, {
        data: { reason: 'UAT 不要了' },
      })
      expect(response.ok()).toBeTruthy()
    } finally {
      await withdrawApi.dispose()
    }

    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto('/workbench/mine')
      const rejectedRow = initiator.page.locator('tbody tr').filter({ hasText: rejected.code })
      await expect(rejectedRow.getByRole('button', { name: '修改并重提' })).toBeVisible()
      await rejectedRow.getByRole('button', { name: '修改并重提' }).click()
      await expect(initiator.page.getByText(/被驳回：/)).toBeVisible()
      await expect(
        initiator.page.getByRole('button', { name: '修改并重新提交' }),
      ).toBeVisible()

      await initiator.page.goto('/workbench/mine')
      const withdrawnRow = initiator.page
        .locator('tbody tr')
        .filter({ hasText: withdrawn.code })
      await withdrawnRow.getByRole('button', { name: '复制为新申请' }).click()
      await expect(initiator.page).toHaveURL(/\/start\/\d+\?draftId=\d+/)
      await expect(initiator.page.getByPlaceholder('请输入事由')).toHaveValue(
        withdrawnData.reason,
      )
    } finally {
      await initiator.context.close()
    }

    // 单节点流程审批人不应看到「退回」按钮
    const running = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('UAT 退回'),
      amount: 60,
    })
    const approver = await openAs(browser, 'lisi')
    try {
      await approver.page.goto('/workbench/todo')
      const row = approver.page.locator('tbody tr').filter({ hasText: running.code })
      await expect(row).toBeVisible()
      await row.locator('td').first().locator('a').click()
      await expect(approver.page.getByText('审批').first()).toBeVisible()
      await expect(
        approver.page.getByRole('button', { name: buttonName('退回') }),
      ).toHaveCount(0)
    } finally {
      await approver.context.close()
    }
  })
})

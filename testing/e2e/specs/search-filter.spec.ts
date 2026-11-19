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

test.describe('@p0 业务字段筛选', () => {
  test('@p0 我发起的按业务字段筛选', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 筛选表单')

    // 配置可检索字段：事由（文本）+ 金额（数字）
    const api = await apiAs('admin')
    try {
      const saved = await api.put(`form-templates/${form.id}/search-fields`, {
        data: { field_keys: ['reason', 'amount'] },
      })
      expect(saved.ok()).toBeTruthy()
    } finally {
      await api.dispose()
    }

    const flow = await createFlowAndPublish(
      form.id,
      'E2E 筛选流程',
      sequentialDefinition([{ id: 'a1', name: '初审', userId: users.lisi.id }]),
    )
    const matched = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 筛中'),
      amount: 500,
    })
    const other = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 筛掉'),
      amount: 50,
    })

    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto('/workbench/mine')

      // 先选中流程，筛选器才会加载该表单的可检索字段
      const flowPicker = initiator.page.getByRole('combobox').first()
      await flowPicker.click()
      await flowPicker.fill(flow.name)
      await flowPicker.press('Enter')
      await expect(initiator.page.getByText('业务字段筛选')).toBeVisible()

      await initiator.page.getByRole('button', { name: '添加条件' }).click()
      const row = initiator.page.locator('.condition-row').first()
      const fieldPicker = row.getByRole('combobox').nth(0)
      // 点击下拉根节点：内部的搜索 input 被选中项 span 盖住，直接点 input 会被拦截
      await row.locator('.field-select').click()
      await fieldPicker.fill('金额')
      await fieldPicker.press('Enter')

      const value = row.getByPlaceholder('值')
      await value.fill('500')
      await value.press('Tab')

      await expect(initiator.page.locator('tbody tr').filter({ hasText: matched.code })).toBeVisible()
      await expect(initiator.page.locator('tbody tr').filter({ hasText: other.code })).toHaveCount(0)
    } finally {
      await initiator.context.close()
    }
  })
})

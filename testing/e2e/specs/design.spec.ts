import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import { createFormAndPublish, uniqueCode } from '../fixtures/factories'
import { buttonName } from '../fixtures/ui'

test.describe('@p0 设计者旅程', () => {
  test('@p0 新建表单、配置字段并发布', async ({ browser }) => {
    const designer = await openAs(browser, 'zhaoliu')
    const formName = uniqueReason('E2E 设计器表单')
    try {
      await designer.page.goto('/admin/forms')
      await designer.page.getByRole('button', { name: '新建表单' }).click()

      const dialog = designer.page.getByRole('dialog')
      await dialog.getByPlaceholder('如：费用报销单').fill(formName)
      await dialog.getByPlaceholder('如：REIMBURSEMENT').fill(uniqueCode('E2E_UI_FORM'))
      await dialog.getByRole('button', { name: buttonName('保存') }).click()

      await expect(designer.page).toHaveURL(/\/admin\/forms\/\d+\/design/)
      await designer.page.getByRole('button', { name: '添加字段' }).click()
      await designer.page.getByText('单行文本', { exact: true }).click()
      await designer.page.getByPlaceholder('展示给填写人的名称').fill('事由')
      await expect(designer.page.getByText('已保存', { exact: true })).toBeVisible({
        timeout: 15_000,
      })

      // 设计器预览：字段按发起阶段可见性渲染
      await designer.page.getByRole('button', { name: '预览' }).click()
      await expect(designer.page.getByText('表单预览')).toBeVisible()
      await expect(designer.page.getByPlaceholder('请输入事由')).toBeVisible()
      await designer.page.locator('.ant-drawer-close').click()
      // Drawer 关闭后 DOM 仍保留，断言输入框不可见即可
      await expect(designer.page.getByPlaceholder('请输入事由')).toBeHidden()

      await designer.page.getByRole('button', { name: buttonName('发布') }).click()
      await designer.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(designer.page.getByText('已发布')).toBeVisible()
    } finally {
      await designer.context.close()
    }
  })

  test('@p0 新建流程、配置审批节点并发布后可发起', async ({ browser }) => {
    const form = await createFormAndPublish('E2E 流程设计器表单')
    const designer = await openAs(browser, 'zhaoliu')
    const flowName = uniqueReason('E2E 设计器流程')
    try {
      await designer.page.goto('/admin/flows')
      await designer.page.getByRole('button', { name: '新建流程' }).click()

      const dialog = designer.page.getByRole('dialog')
      await dialog.getByPlaceholder('如：费用报销流程').fill(flowName)
      const formPicker = dialog.getByRole('combobox').first()
      await formPicker.click()
      await formPicker.fill(form.name)
      await formPicker.press('Enter')
      await dialog
        .getByPlaceholder('如：REIMBURSEMENT_FLOW')
        .fill(uniqueCode('E2E_UI_FLOW'))
      await dialog.getByRole('button', { name: buttonName('保存') }).click()

      await expect(designer.page).toHaveURL(/\/admin\/flows\/\d+\/design/)
      // 新建流程自带一个「部门经理审批」节点；从默认配置出发核对处理人来源
      await designer.page.getByRole('tab', { name: '处理人' }).click()
      await expect(designer.page.getByText('部门主管').first()).toBeVisible()

      await designer.page.getByRole('button', { name: buttonName('发布') }).click()
      await designer.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(designer.page.getByText('已发布')).toBeVisible()
    } finally {
      await designer.context.close()
    }

    // 设计者发布 → 发起人立刻能在发起中心看到
    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto('/start-center')
      await expect(
        initiator.page.getByTestId('flow-card').filter({ hasText: flowName }),
      ).toBeVisible()
    } finally {
      await initiator.context.close()
    }
  })
})

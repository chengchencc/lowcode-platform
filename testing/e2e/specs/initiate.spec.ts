import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'

test.describe('@p0 发起人旅程', () => {
  test('@p0 从发起中心填写并提交请假申请', async ({ browser }) => {
    const { context, page } = await openAs(browser, 'zhangsan')
    try {
      await page.goto('/start-center')
      await page.getByTestId('flow-card').filter({ hasText: '请假申请' }).click()
      await expect(page).toHaveURL(/\/start\/\d+/)

      // 假别：下拉选项由表单配置下发；占位符 span 被搜索输入框盖住，直接点 combobox
      // 下拉支持搜索：输入选项名后回车，比点被虚拟列表重渲染的 option 稳定
      const leaveType = page.getByRole('combobox')
      await leaveType.click()
      await leaveType.fill('年假')
      await leaveType.press('Enter')

      // 起止日期：输入框只读，走日期面板；选「今天」保持用例与运行日期无关
      const dates = page.getByPlaceholder('请选择日期')
      const panel = page.locator('.ant-picker-dropdown').filter({ visible: true }).last()
      for (const index of [0, 1]) {
        await dates.nth(index).click()
        await expect(panel).toBeVisible()
        // 只点当前打开面板里的「今天」，避免上一块面板关闭动画期间点到隐藏元素
        await panel.locator('td.ant-picker-cell-today').first().click()
        await expect(dates.nth(index)).not.toHaveValue('')
      }

      const reason = uniqueReason('E2E 发起')
      await page.getByPlaceholder('请输入事由').fill(reason)
      await page.getByRole('button', { name: '提交审批' }).click()

      await expect(page).toHaveURL(/\/instance\/\d+/)
      await expect(page.getByText('审批中').first()).toBeVisible()
      await expect(page.getByText('直属上级审批').first()).toBeVisible()
      await expect(page.getByText('发起人：张三').first()).toBeVisible()

      // 界面说提交成功还不够：回读接口确认实例与表单值真的落了库
      const instanceId = Number(page.url().match(/\/instance\/(\d+)/)?.[1])
      expect(instanceId).toBeGreaterThan(0)
      const rendered = await renderAs('zhangsan', instanceId)
      expect(rendered.instance.status).toBe('RUNNING')
      expect(rendered.instance.initiator_name).toBe('张三')
      expect(rendered.values.reason).toBe(reason)
    } finally {
      await context.close()
    }
  })

  test('@p0 填写内容自动暂存，可在发起中心续填', async ({ browser }) => {
    const { context, page } = await openAs(browser, 'zhangsan')
    try {
      await page.goto('/start-center')
      await page.getByTestId('flow-card').filter({ hasText: '请假申请' }).click()

      const reason = uniqueReason('E2E 草稿')
      await page.getByPlaceholder('请输入事由').fill(reason)
      // 自动暂存有 2s 防抖；等界面自己确认，避免用固定 sleep
      await expect(page.getByText('已暂存', { exact: true })).toBeVisible({ timeout: 15_000 })

      await page.goto('/start-center')
      await expect(page.getByText('我的草稿')).toBeVisible()
      await page
        .getByTestId('draft-item')
        .first()
        .getByRole('button', { name: '继续填写' })
        .click()
      await expect(page).toHaveURL(/draftId=\d+/)
      await expect(page.getByPlaceholder('请输入事由')).toHaveValue(reason)
    } finally {
      await context.close()
    }
  })
})

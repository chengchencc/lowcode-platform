import { expect, test, type Page } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  submitFor,
} from '../fixtures/factories'
import { buttonName, openTodoByCode } from '../fixtures/ui'

const MOBILE = { width: 390, height: 844 }

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
}

test.describe('@p0 移动端与打印', () => {
  test('@p0 390px 发起中心与填写页无横向溢出', async ({ browser }) => {
    const { context, page } = await openAs(browser, 'zhangsan')
    try {
      await page.setViewportSize(MOBILE)
      await page.goto('/start-center')
      await expect(page.getByText('发起新流程')).toBeVisible()
      await expectNoHorizontalOverflow(page)

      await page.getByTestId('flow-card').filter({ hasText: '请假申请' }).click()
      await expect(page).toHaveURL(/\/start\/\d+/)
      await expect(page.getByPlaceholder('请输入事由')).toBeVisible()
      await expectNoHorizontalOverflow(page)
    } finally {
      await context.close()
    }
  })

  test('@p0 390px 审批详情可读且打印调用浏览器打印', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 移动打印表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 移动打印流程',
      sequentialDefinition([{ id: 'a1', name: '初审', userId: users.lisi.id }]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 移动打印'),
      amount: 100,
    })

    const { context, page } = await openAs(browser, 'lisi')
    try {
      await page.setViewportSize(MOBILE)
      // 替换 window.print，验证按钮真的触发了打印入口
      await context.addInitScript(() => {
        ;(window as unknown as { __printed?: number }).__printed = 0
        window.print = () => {
          const holder = window as unknown as { __printed?: number }
          holder.__printed = (holder.__printed ?? 0) + 1
        }
      })
      await openTodoByCode(page, instance.code, instance.id)
      await expect(page.getByText('初审').first()).toBeVisible()
      await expectNoHorizontalOverflow(page)

      await page.getByRole('button', { name: buttonName('打印') }).click()
      const printed = await page.evaluate(
        () => (window as unknown as { __printed?: number }).__printed ?? 0,
      )
      expect(printed).toBe(1)
    } finally {
      await context.close()
    }
  })
})

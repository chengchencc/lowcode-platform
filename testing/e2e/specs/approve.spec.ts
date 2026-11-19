import { expect, test, type Page } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, submitLeaveAsZhangsan, uniqueReason } from '../fixtures/data'

/** 在待办列表里按实例单号定位并打开；避免多条「请假申请」互相干扰。 */
async function openTodoByCode(
  page: Page,
  code: string,
  instanceId: number,
): Promise<void> {
  await page.goto('/workbench/todo')
  const search = page.getByPlaceholder('标题或实例单号')
  await search.fill(code)
  await search.press('Enter')

  const row = page.locator('tbody tr').filter({ hasText: code })
  await expect(row).toBeVisible()
  await row.locator('td').first().locator('a').click()
  await expect(page).toHaveURL(new RegExp(`/instance/${instanceId}`))
}

test.describe('@p0 审批人旅程', () => {
  test('@p0 待办打开实例、填写意见并同意', async ({ browser }) => {
    const reason = uniqueReason('E2E 同意')
    const instance = await submitLeaveAsZhangsan(reason)

    const { context, page } = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(page, instance.code, instance.id)
      await expect(page.getByText('直属上级审批').first()).toBeVisible()

      await page.getByRole('button', { name: /同\s*意/ }).click()
      const opinion = uniqueReason('同意意见')
      await page.getByPlaceholder('选填', { exact: true }).fill(opinion)
      await page.getByRole('button', { name: '确认同意' }).click()

      await expect(page.getByText('已同意')).toBeVisible()
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
      await page.getByRole('button', { name: /同\s*意/ }).click()
      await page.getByRole('button', { name: '确认同意' }).click()
      await expect(page.getByText('已同意')).toBeVisible()

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
})

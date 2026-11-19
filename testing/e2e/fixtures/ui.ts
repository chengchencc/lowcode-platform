import { expect, type Page } from '@playwright/test'

/** 在待办列表里按实例单号定位并打开；避免多条同名流程互相干扰。 */
export async function openTodoByCode(page: Page, code: string, instanceId: number): Promise<void> {
  await page.goto('/workbench/todo')
  const search = page.getByPlaceholder('标题或实例单号')
  await search.fill(code)
  await search.press('Enter')

  const row = page.locator('tbody tr').filter({ hasText: code })
  await expect(row).toBeVisible()
  await row.locator('td').first().locator('a').click()
  await expect(page).toHaveURL(new RegExp(`/instance/${instanceId}`))
}

/** antd 会在两个汉字的按钮里插空格，例如「同 意」「驳 回」。 */
export function buttonName(text: string): RegExp {
  return new RegExp(text.split('').join('\\s*'))
}

export async function approveViaUi(page: Page, opinion?: string): Promise<void> {
  await page.getByRole('button', { name: buttonName('同意') }).click()
  if (opinion) {
    await page.getByPlaceholder('选填', { exact: true }).fill(opinion)
  }
  await page.getByRole('button', { name: '确认同意' }).click()
  await expect(page.getByText('已同意')).toBeVisible()
}

export async function rejectViaUi(page: Page, opinion: string): Promise<void> {
  await page.getByRole('button', { name: buttonName('驳回') }).click()
  await page.getByPlaceholder('必填', { exact: true }).fill(opinion)
  await page.getByRole('button', { name: '确认驳回' }).click()
  await expect(page.getByText('已驳回').first()).toBeVisible()
}

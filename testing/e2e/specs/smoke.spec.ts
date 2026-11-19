import { expect, test } from '@playwright/test'

import { API_BASE, openAs } from '../fixtures/auth'

test.describe('@p0 冒烟与角色可见性', () => {
  test('@p0 后端与数据库就绪', async ({ request }) => {
    const response = await request.get(`${API_BASE}/readyz`)
    expect(response.ok()).toBeTruthy()
    const body = (await response.json()) as { status: string; database: string }
    expect(body.status).toBe('ok')
    expect(['sqlite', 'mysql', 'postgresql']).toContain(body.database)
  })

  test('@p0 管理员通过登录页登录并看到管理菜单', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('请输入用户名').fill('admin')
    await page.getByPlaceholder('请输入密码').fill('admin123456')
    // antd 会在两个中文字之间插入空格，可访问名实际是「登 录」
    await page.getByRole('button', { name: /登\s*录/ }).click()

    await expect(page).toHaveURL(/\/dashboard/)
    const menu = page.getByRole('menu')
    await expect(menu.getByText('发起中心')).toBeVisible()
    await expect(menu.getByText('审批管理')).toBeVisible()
    await expect(menu.getByText('组织管理')).toBeVisible()
    await expect(menu.getByText('操作审计')).toBeVisible()
  })

  test('@p0 错误密码在登录页就地提示', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('请输入用户名').fill('admin')
    await page.getByPlaceholder('请输入密码').fill('wrong-password')
    // antd 会在两个中文字之间插入空格，可访问名实际是「登 录」
    await page.getByRole('button', { name: /登\s*录/ }).click()

    await expect(page.getByText('用户名或密码错误')).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
  })

  test('@p0 普通用户看不到审批与组织管理菜单', async ({ browser }) => {
    const { context, page } = await openAs(browser, 'zhangsan')
    try {
      await page.goto('/dashboard')
      const menu = page.getByRole('menu')
      await expect(menu.getByText('发起中心')).toBeVisible()
      await expect(menu.getByText('审批管理')).toHaveCount(0)
      await expect(menu.getByText('组织管理')).toHaveCount(0)
    } finally {
      await context.close()
    }
  })

  test('@p0 设计者看到模板菜单但看不到实例与组织管理', async ({ browser }) => {
    const { context, page } = await openAs(browser, 'zhaoliu')
    try {
      await page.goto('/dashboard')
      const menu = page.getByRole('menu')
      await expect(menu.getByText('审批管理')).toBeVisible()
      await expect(menu.getByText('表单模板')).toBeVisible()
      await expect(menu.getByText('流程模板')).toBeVisible()
      await expect(menu.getByText('实例管理')).toHaveCount(0)
      await expect(menu.getByText('组织管理')).toHaveCount(0)
    } finally {
      await context.close()
    }
  })

  test('@p0 普通用户发起中心能看到示例流程', async ({ browser }) => {
    const { context, page } = await openAs(browser, 'zhangsan')
    try {
      await page.goto('/start-center')
      await expect(page.getByText('发起新流程')).toBeVisible()
      await expect(page.getByText('请假申请', { exact: true })).toBeVisible()
      await expect(page.getByText('费用报销', { exact: true })).toBeVisible()
    } finally {
      await context.close()
    }
  })
})

import { expect, test, type Page } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'
import {
  approveViaApi,
  createFormAndPublish,
  findAssignment,
  seedUsers,
  submitFor,
  todoInstanceIds,
} from '../fixtures/factories'
import { buttonName } from '../fixtures/ui'

async function createFlowViaUi(page: Page, formName: string, flowName: string): Promise<void> {
  await page.goto('/admin/flows')
  await page.getByRole('button', { name: '新建流程' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByPlaceholder('如：费用报销流程').fill(flowName)
  const formPicker = dialog.getByRole('combobox').first()
  await formPicker.click()
  await formPicker.fill(formName)
  await formPicker.press('Enter')
  await dialog.getByRole('button', { name: buttonName('保存') }).click()
  await expect(page).toHaveURL(/\/admin\/flows\/\d+\/design/)
}

async function configureUserSource(page: Page, userName: string): Promise<void> {
  await page.getByRole('tab', { name: '处理人' }).click()
  await page.getByRole('button', { name: '添加来源' }).click()

  // 新来源默认「指定角色」；选项顺序 user 在 role 之前，上移一格即「指定人员」
  await page.locator('.source-type').last().click()
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('Enter')

  const picker = page.locator('.source-value').last()
  await picker.click()
  await page.keyboard.type(userName)
  await page.keyboard.press('Enter')
}

async function addMainNode(page: Page, label: string): Promise<void> {
  await page.getByRole('button', { name: '添加到主线' }).click()
  await page.getByText(label, { exact: true }).click()
}

test.describe('@p0 设计器复杂配置', () => {
  test('@p0 配置条件分支、并行组与字段权限并运行', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 复杂设计器表单')
    const designer = await openAs(browser, 'zhaoliu')
    const flowName = uniqueReason('E2E 复杂流程')
    let flowId = 0
    try {
      await createFlowViaUi(designer.page, form.name, flowName)
      await designer.page.getByText('清单', { exact: true }).click()

      // 1. 条件分支：金额 > 1000 走分支
      await addMainNode(designer.page, '条件分支')
      await designer.page.getByRole('tab', { name: '分支' }).click()
      await designer.page.getByRole('button', { name: '添加条件' }).click()

      await designer.page.locator('.cond-field').click()
      await designer.page.keyboard.type('金额')
      await designer.page.keyboard.press('Enter')
      await designer.page.locator('.cond-cmp').click()
      await designer.page.keyboard.press('ArrowDown')
      await designer.page.keyboard.press('ArrowDown')
      await designer.page.keyboard.press('Enter')
      await designer.page.getByPlaceholder('值').fill('1000')

      // 2. 分支内审批节点 + 指定李四
      await designer.page.getByRole('button', { name: '添加到分支' }).click()
      // 主线的下拉菜单仍挂在 DOM 里，只点当前可见的那份
      await designer.page
        .getByText('审批节点', { exact: true })
        .filter({ visible: true })
        .last()
        .click()
      await configureUserSource(designer.page, '李四')

      // 3. 该节点把「金额」隐藏
      await designer.page.getByRole('tab', { name: '字段权限' }).click()
      // 单字段覆盖在按分区折叠的面板里，先展开「申请」分区
      await designer.page
        .locator('.perm-panel .ant-collapse-header')
        .filter({ hasText: '申请' })
        .first()
        .click()
      const amountRow = designer.page.locator('.perm-panel .row').filter({ hasText: '金额' }).first()
      await amountRow.locator('.row-control').click()
      // 打开时高亮第一项「隐藏」，直接回车
      await designer.page.keyboard.press('Enter')
      await expect(amountRow.getByText('隐藏').first()).toBeVisible()

      // 4. 主线并行组：两个会签成员分别指定李四、王五
      await addMainNode(designer.page, '并行组')
      // 默认节点叫「部门经理审批」；这里的 3 个是分支节点 + 两个并行成员
      const approvalNodes = designer.page.locator('.node-item').filter({ hasText: '审批节点' })
      await expect(approvalNodes).toHaveCount(3)
      await approvalNodes.nth(1).click()
      await configureUserSource(designer.page, '李四')
      await approvalNodes.nth(2).click()
      await configureUserSource(designer.page, '王五')

      await designer.page.getByRole('button', { name: buttonName('发布') }).click()
      await designer.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(designer.page.getByText('已发布')).toBeVisible()

      flowId = Number(designer.page.url().match(/\/admin\/flows\/(\d+)\//)?.[1] ?? 0)
    } finally {
      await designer.context.close()
    }
    expect(flowId).toBeGreaterThan(0)

    // 5. 运行：小额跳过分支直接到并行组；大额先走分支，再到并行组
    const small = await submitFor('zhangsan', flowId, {
      reason: uniqueReason('E2E 复杂-小额'),
      amount: 500,
    })
    await approveViaApi('lisi', small.id, '初审')
    expect(await todoInstanceIds('wangwu')).toContain(small.id)
    await approveViaApi('lisi', small.id, '会签')
    await approveViaApi('wangwu', small.id, '会签')
    expect((await renderAs('zhangsan', small.id)).instance.status).toBe('APPROVED')

    const large = await submitFor('zhangsan', flowId, {
      reason: uniqueReason('E2E 复杂-大额'),
      amount: 1500,
    })
    await approveViaApi('lisi', large.id, '初审')
    // 分支节点在并行组之前：此时王五不应收到待办
    expect(await todoInstanceIds('wangwu')).not.toContain(large.id)
    const branchTask = await findAssignment('lisi', large.id)
    await approveViaApi('lisi', large.id, '分支审批')
    expect(await todoInstanceIds('wangwu')).toContain(large.id)
    await approveViaApi('lisi', large.id, '会签')
    await approveViaApi('wangwu', large.id, '会签')
    expect((await renderAs('zhangsan', large.id)).instance.status).toBe('APPROVED')
    expect(branchTask.node_name).toBeTruthy()
  })
})

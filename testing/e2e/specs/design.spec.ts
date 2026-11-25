import { readFile } from 'node:fs/promises'

import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  uniqueCode,
} from '../fixtures/factories'
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
      await expect(designer.page.getByText('已发布', { exact: true })).toBeVisible()

      // 发布后停留在已发布版本，不应凭空多出一个草稿
      await expect(designer.page.getByText('已冻结，不可编辑')).toBeVisible()
      await expect(designer.page.getByText(/v1 · 已发布/)).toBeVisible()
      await expect(designer.page.getByText(/· 草稿/)).toHaveCount(0)

      // 再次打开设计器也只是查看发布版，不会又冒出一个草稿
      await designer.page.reload()
      await expect(designer.page.getByText(/v1 · 已发布/)).toBeVisible()
      await expect(designer.page.getByText(/· 草稿/)).toHaveCount(0)

      // 需要继续编辑时显式新建草稿；不需要时可以删除
      await designer.page.getByRole('button', { name: '新建草稿' }).click()
      await expect(designer.page.getByText(/v2 · 草稿/)).toBeVisible()
      await designer.page.getByRole('button', { name: '删除草稿' }).click()
      await designer.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(designer.page.getByRole('button', { name: '新建草稿' })).toBeVisible()
      await expect(designer.page.getByText(/v1 · 已发布/)).toBeVisible()
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

      // 流程级设置：已办处理人打开运行中单据时可见全部区域，且能持久化
      await designer.page.getByRole('button', { name: '流程设置' }).click()
      const settings = designer.page.getByRole('dialog')
      await expect(settings.getByText('已办处理人打开运行中单据时')).toBeVisible()
      await settings.getByRole('radio', { name: '全部区域只读' }).click()
      await expect(designer.page.getByText('已保存', { exact: true })).toBeVisible({
        timeout: 15_000,
      })
      await settings.locator('.ant-modal-close').click()
      await designer.page.reload()
      await designer.page.getByRole('button', { name: '流程设置' }).click()
      await expect(
        designer.page.getByRole('dialog').getByRole('radio', { name: '全部区域只读' }),
      ).toBeChecked()
      await designer.page.getByRole('dialog').locator('.ant-modal-close').click()

      // 新建流程自带一个「部门经理审批」节点；从默认配置出发核对处理人来源
      await designer.page.getByRole('tab', { name: '处理人' }).click()
      await expect(designer.page.getByText('部门主管').first()).toBeVisible()

      await designer.page.getByRole('button', { name: buttonName('发布') }).click()
      await designer.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(designer.page.getByText('已发布', { exact: true })).toBeVisible()

      // 发布后停留在已发布版本，不应凭空多出一个草稿
      await expect(designer.page.getByText('已冻结，不可编辑')).toBeVisible()
      await expect(designer.page.getByText(/v1 · 已发布/)).toBeVisible()
      await expect(designer.page.getByText(/· 草稿/)).toHaveCount(0)

      await designer.page.reload()
      await expect(designer.page.getByText(/v1 · 已发布/)).toBeVisible()
      await expect(designer.page.getByText(/· 草稿/)).toHaveCount(0)

      await designer.page.getByRole('button', { name: '新建草稿' }).click()
      await expect(designer.page.getByText(/v2 · 草稿/)).toBeVisible()
      await designer.page.getByRole('button', { name: '删除草稿' }).click()
      await designer.page.getByRole('button', { name: buttonName('确定') }).click()
      await expect(designer.page.getByRole('button', { name: '新建草稿' })).toBeVisible()
      await expect(designer.page.getByText(/v1 · 已发布/)).toBeVisible()
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

  test('@p1 流程配置可导出 JSON 并导入为草稿', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 迁移源表单')
    const flowName = uniqueReason('E2E 迁移源流程')
    await createFlowAndPublish(
      form.id,
      flowName,
      sequentialDefinition([{ id: 'a1', name: '审批', userId: users.lisi.id }]),
    )

    const designer = await openAs(browser, 'zhaoliu')
    try {
      await designer.page.goto('/admin/flows')

      // 导出：下载文件内容应带元信息与源表单名称
      const row = designer.page.locator('tbody tr').filter({ hasText: flowName })
      const [download] = await Promise.all([
        designer.page.waitForEvent('download'),
        row.getByRole('button', { name: buttonName('导出') }).click(),
      ])
      const path = await download.path()
      if (!path) throw new Error('浏览器没有给出下载文件路径')
      const exported = JSON.parse(await readFile(path, 'utf8')) as {
        name: string
        form_name: string
        definition: Record<string, unknown>
      }
      expect(exported.name).toBe(flowName)
      expect(exported.form_name).toBe(form.name)
      expect(exported.definition).toBeTruthy()

      // 导入：Upload 的隐藏 input 直接投喂文件即可；选回同一张已发布表单，生成草稿并进入设计器
      await designer.page.locator('input[type="file"]').setInputFiles({
        name: `${flowName}.json`,
        mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify(exported)),
      })

      const dialog = designer.page.getByRole('dialog')
      await expect(dialog.getByText(`来源：${flowName}`)).toBeVisible()
      // 源表单编码/名称能对上时预选目标表单；对不上才需要人工选择
      await expect(dialog.locator('.ant-select-selection-item')).toHaveText(form.name)
      await dialog.getByRole('button', { name: buttonName('导入') }).click()

      await expect(designer.page).toHaveURL(/\/admin\/flows\/\d+\/design/)
      await expect(designer.page.getByText(/v1\s*·\s*草稿/)).toBeVisible()
    } finally {
      await designer.context.close()
    }
  })
})

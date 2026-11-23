import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { uniqueReason } from '../fixtures/data'
import {
  createFlowAndPublish,
  createFormAndPublish,
  seedUsers,
  sequentialDefinition,
  submitFor,
} from '../fixtures/factories'
import { approveViaUi, openTodoByCode } from '../fixtures/ui'

const FIELD_LABEL = '合同编号'
const FIELD_VALUE = 'HT-E2E-001'

test.describe('@p0 运行中追加字段', () => {
  test('@p0 管理员追加字段后，当前处理人可填、后续节点与归档可见', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 追加字段表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 追加字段流程',
      sequentialDefinition([
        { id: 'a1', name: '初审', userId: users.lisi.id },
        { id: 'a2', name: '复核', userId: users.wangwu.id },
      ]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 追加字段'),
      amount: 100,
    })

    // 管理员在运行中的实例上追加字段，默认只让当前节点（初审）填写
    const admin = await openAs(browser, 'admin')
    try {
      await admin.page.goto(`/instance/${instance.id}`)
      await admin.page.getByRole('button', { name: '追加字段' }).click()
      const dialog = admin.page.getByRole('dialog')
      await dialog.getByPlaceholder('如：合同编号').fill(FIELD_LABEL)
      await dialog.getByRole('button', { name: /^追\s*加$/ }).click()
      await expect(admin.page.getByText(`已追加字段「${FIELD_LABEL}」`)).toBeVisible()
    } finally {
      await admin.context.close()
    }

    // 当前处理人：字段可编辑，填写后随本次同意落库
    const first = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(first.page, instance.code, instance.id)
      const input = first.page.getByPlaceholder(`请输入${FIELD_LABEL}`)
      await expect(input).toBeVisible()
      await input.fill(FIELD_VALUE)
      await approveViaUi(first.page, '已补充合同编号')
    } finally {
      await first.context.close()
    }

    // 后续节点：只读可见，不能修改
    const second = await openAs(browser, 'wangwu')
    try {
      await openTodoByCode(second.page, instance.code, instance.id)
      // 详情页同时渲染打印视图，同一值会出现两处；断言第一处即可
      await expect(second.page.getByText(FIELD_VALUE).first()).toBeVisible()
      await expect(second.page.getByPlaceholder(`请输入${FIELD_LABEL}`)).toHaveCount(0)
      await approveViaUi(second.page, '复核通过')
    } finally {
      await second.context.close()
    }

    // 归档视角：动态字段仍可见
    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto(`/instance/${instance.id}`)
      await expect(initiator.page.getByText('已通过').first()).toBeVisible()
      await expect(initiator.page.getByText(FIELD_LABEL).first()).toBeVisible()
      await expect(initiator.page.getByText(FIELD_VALUE).first()).toBeVisible()
    } finally {
      await initiator.context.close()
    }
  })

  test('@p0 非管理员看不到追加字段入口', async ({ browser }) => {
    const users = await seedUsers()
    const form = await createFormAndPublish('E2E 追加字段权限表单')
    const flow = await createFlowAndPublish(
      form.id,
      'E2E 追加字段权限流程',
      sequentialDefinition([{ id: 'a1', name: '初审', userId: users.lisi.id }]),
    )
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 追加字段入口'),
      amount: 100,
    })

    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto(`/instance/${instance.id}`)
      await expect(
        initiator.page.getByRole('button', { name: '追加字段' }),
      ).toHaveCount(0)
    } finally {
      await initiator.context.close()
    }

    // 有设计者角色、但不是管理员/处理人时，服务端也不允许改别人的实例
    const designer = await openAs(browser, 'zhaoliu')
    try {
      await designer.page.goto(`/instance/${instance.id}`)
      await expect(designer.page).toHaveURL(/\/workbench\/mine/)
    } finally {
      await designer.context.close()
    }
  })
})

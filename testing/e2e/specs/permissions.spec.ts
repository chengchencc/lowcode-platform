import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'
import {
  approvalNode,
  approveViaApi,
  createFlowAndPublish,
  createFormAndPublish,
  findAssignment,
  seedUsers,
  simpleFormSchema,
  submitFor,
  type FieldSpec,
} from '../fixtures/factories'
import { approveViaUi, openTodoByCode } from '../fixtures/ui'

const SECRET_LABEL = '补充信息'

async function setup() {
  const users = await seedUsers()
  const secretField: FieldSpec = { key: 'secret', label: SECRET_LABEL, type: 'text' }
  const form = await createFormAndPublish('E2E 字段权限表单', simpleFormSchema([secretField]))
  const flow = await createFlowAndPublish(form.id, 'E2E 字段权限流程', {
    model_version: 1,
    start: { id: 'start', name: '开始', type: 'start', fields_permission: null },
    steps: [
      approvalNode('a1', '审批', users.lisi.id, {
        base: 'readonly',
        overrides: { secret: 'hidden' },
      }),
    ],
    end: { id: 'end', name: '结束', type: 'end' },
  })
  const secretValue = uniqueReason('机密内容')
  const instance = await submitFor('zhangsan', flow.id, {
    reason: uniqueReason('E2E 权限'),
    amount: 100,
    secret: secretValue,
  })
  return { users, instance, secretValue }
}

test.describe('@p0 字段与实例权限', () => {
  test('@p0 审批节点隐藏的字段不出现在界面和接口响应中', async ({ browser }) => {
    const { instance, secretValue } = await setup()
    const assignment = await findAssignment('lisi', instance.id)

    // 当前处理人视角：补充信息被节点矩阵隐藏
    const handlerView = await renderAs('lisi', instance.id, assignment.assignment_id)
    expect(handlerView.values.secret).toBeUndefined()

    const handler = await openAs(browser, 'lisi')
    try {
      await openTodoByCode(handler.page, instance.code, instance.id)
      await expect(handler.page.getByText('事由').first()).toBeVisible()
      await expect(handler.page.getByText(SECRET_LABEL)).toHaveCount(0)
      await expect(handler.page.getByText(secretValue)).toHaveCount(0)
      await approveViaUi(handler.page, '同意')
    } finally {
      await handler.context.close()
    }
  })

  test('@p0 无关用户直接打开实例会被拒绝', async ({ browser }) => {
    const { instance } = await setup()

    const outsider = await openAs(browser, 'zhaoliu')
    try {
      await outsider.page.goto(`/instance/${instance.id}`)
      await expect(outsider.page).toHaveURL(/\/workbench\/mine/)
      await expect(outsider.page.getByText('你没有权限查看该单据').first()).toBeVisible()
    } finally {
      await outsider.context.close()
    }
  })

  test('@p0 终态后归档视角字段完整可见', async ({ browser }) => {
    const { instance, secretValue } = await setup()
    await approveViaApi('lisi', instance.id, '通过')

    // 发起人终态视角：补充字段揭晓
    const initiator = await openAs(browser, 'zhangsan')
    try {
      await initiator.page.goto(`/instance/${instance.id}`)
      await expect(initiator.page.getByText('已通过').first()).toBeVisible()
      await expect(initiator.page.getByText(SECRET_LABEL).first()).toBeVisible()
      await expect(initiator.page.getByText(secretValue).first()).toBeVisible()
    } finally {
      await initiator.context.close()
    }

    // 管理员终态视角：同样完整可见
    const admin = await openAs(browser, 'admin')
    try {
      await admin.page.goto(`/instance/${instance.id}`)
      await expect(admin.page.getByText(SECRET_LABEL).first()).toBeVisible()
      await expect(admin.page.getByText(secretValue).first()).toBeVisible()
    } finally {
      await admin.context.close()
    }
  })
})

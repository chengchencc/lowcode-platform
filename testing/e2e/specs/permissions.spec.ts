import { expect, test } from '@playwright/test'

import { openAs } from '../fixtures/auth'
import { renderAs, uniqueReason } from '../fixtures/data'
import {
  actAs,
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

  test('@p0 已办处理人重新打开运行中单据仍能看到本人处理过的区域', async ({ browser }) => {
    const users = await seedUsers()
    const schema = simpleFormSchema()
    const sections = schema.sections as Array<Record<string, unknown>>
    sections.push({
      key: 'sec_supplement',
      title: '补充资料',
      stage: 'supplement',
      sort: 1,
      fields: [
        {
          key: 'secret',
          label: SECRET_LABEL,
          type: 'text',
          sort: 0,
          required: false,
          visible_at_start: false,
        },
      ],
    })
    const form = await createFormAndPublish('E2E 分区放开表单', schema)
    const flow = await createFlowAndPublish(form.id, 'E2E 分区放开流程', {
      model_version: 1,
      start: { id: 'start', name: '开始', type: 'start', fields_permission: null },
      steps: [
        approvalNode('a1', '初审', users.lisi.id, {
          base: 'hidden',
          overrides: { reason: 'readonly', amount: 'readonly', secret: 'editable' },
        }),
        approvalNode('a2', '终审', users.wangwu.id, {
          base: 'hidden',
          overrides: { reason: 'readonly' },
        }),
      ],
      end: { id: 'end', name: '结束', type: 'end' },
    })
    const secretValue = uniqueReason('补充内容')
    const instance = await submitFor('zhangsan', flow.id, {
      reason: uniqueReason('E2E 分区'),
      amount: 200,
    })

    // 初审节点才放开补充资料分区；李四填写后流转到终审。
    const assignment = await findAssignment('lisi', instance.id)
    await actAs('lisi', assignment.assignment_id, 'AGREE', {
      opinion: '补齐资料',
      fieldPatch: { secret: secretValue },
    })

    // 李四已办：本人节点开放过的区域仍在，且只读。
    const handled = await renderAs('lisi', instance.id)
    expect(handled.values.secret).toBe(secretValue)
    expect(handled.values.reason).toBeTruthy()
    expect(handled.allowed_actions).toEqual([])

    // 尚未到达该区域的终审人与发起人仍看不到补充资料。
    expect((await renderAs('wangwu', instance.id)).values.secret).toBeUndefined()
    expect((await renderAs('zhangsan', instance.id)).values.secret).toBeUndefined()

    const approver = await openAs(browser, 'lisi')
    try {
      await approver.page.goto('/workbench/done')
      const search = approver.page.getByPlaceholder('标题或实例单号')
      await search.fill(instance.code)
      await search.press('Enter')
      const row = approver.page.locator('tbody tr').filter({ hasText: instance.code })
      await expect(row).toBeVisible()
      await row.getByRole('button', { name: '查看' }).click()
      await expect(approver.page).toHaveURL(new RegExp(`/instance/${instance.id}`))
      await expect(approver.page.getByText(SECRET_LABEL).first()).toBeVisible()
      await expect(approver.page.getByText(secretValue).first()).toBeVisible()
      await expect(approver.page.getByText('事由').first()).toBeVisible()
    } finally {
      await approver.context.close()
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

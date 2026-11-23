import { expect, type APIRequestContext } from '@playwright/test'

import { apiAs, type Role } from './auth'
import type { InstanceBrief } from './data'

/** 与 testing/api/support/factories.py 保持同样的定义形状。 */

export interface SeedUser {
  id: number
  username: string
  real_name: string
  dept_id?: number | null
}

let seedPromise: Promise<Record<string, SeedUser>> | null = null

/** 管理员视角的账号表（带 id），用于把定义里的用户名换成数据库 id。 */
export async function seedUsers(): Promise<Record<string, SeedUser>> {
  if (!seedPromise) {
    seedPromise = (async () => {
      const api = await apiAs('admin')
      try {
        const response = await api.get('users?size=100')
        expect(response.ok()).toBeTruthy()
        const body = (await response.json()) as { items: SeedUser[] }
        return Object.fromEntries(body.items.map((user) => [user.username, user]))
      } finally {
        await api.dispose()
      }
    })()
  }
  return seedPromise
}

export async function userId(username: string): Promise<number> {
  const users = await seedUsers()
  const user = users[username]
  if (!user) throw new Error(`种子账号不存在：${username}`)
  return user.id
}

let suffix = 0

/** 表单/流程编码要求大写字母开头、只含大写/数字/下划线。 */
export function uniqueCode(prefix: string): string {
  suffix += 1
  return `${prefix}_${Date.now()}_${suffix}`
}

// --------------------------------------------------------------------------- 表单

export interface FieldSpec {
  key: string
  label: string
  type?: string
  required?: boolean
  visibleAtStart?: boolean
  options?: Array<{ label: string; value: string }>
}

export function simpleFormSchema(extraFields: FieldSpec[] = [], titleField = 'reason'): Record<string, unknown> {
  const fields = [
    { key: 'reason', label: '事由', type: 'text', sort: 0, required: true, visible_at_start: true },
    { key: 'amount', label: '金额', type: 'number', sort: 1, required: false, visible_at_start: true },
    ...extraFields.map((field, index) => ({
      key: field.key,
      label: field.label,
      type: field.type ?? 'text',
      sort: index + 2,
      required: field.required ?? false,
      visible_at_start: field.visibleAtStart ?? true,
      ...(field.options ? { options: field.options } : {}),
    })),
  ]
  return {
    model_version: 1,
    layout: { label_position: 'top', columns: 1 },
    title_field: titleField,
    rules: [],
    sections: [{ key: 'sec_apply', title: '申请', stage: 'apply', sort: 0, fields }],
  }
}

export async function createFormAndPublish(
  name: string,
  schema: Record<string, unknown> = simpleFormSchema(),
): Promise<{ id: number; name: string }> {
  const api = await apiAs('admin')
  try {
    const created = await api.post('form-templates', {
      data: { name, code: uniqueCode('E2E_FORM'), schema_data: schema },
    })
    expect(created.ok()).toBeTruthy()
    const form = (await created.json()) as { id: number; name: string }

    const versions = await api.get(`form-templates/${form.id}/versions`)
    expect(versions.ok()).toBeTruthy()
    const draft = ((await versions.json()) as Array<{ id: number; status: string }>).find(
      (item) => item.status === 'DRAFT',
    )
    if (!draft) throw new Error('新建表单没有草稿版本')

    const published = await api.post(`form-versions/${draft.id}/publish`, {
      data: { remark: 'E2E 自动发布' },
    })
    expect(published.ok()).toBeTruthy()
    return form
  } finally {
    await api.dispose()
  }
}

// --------------------------------------------------------------------------- 流程定义

export function approvalNode(
  id: string,
  name: string,
  approverUserId: number,
  options: {
    base?: string
    overrides?: Record<string, string>
    returnTargets?: string[]
    opinionRequired?: boolean
  } = {},
): Record<string, unknown> {
  return {
    id,
    name,
    type: 'approval',
    assignee: {
      mode: 'SINGLE',
      sources: [{ type: 'user', user_ids: [approverUserId] }],
      on_empty: 'to_admin',
      initiator_select: null,
    },
    reject_policy: 'reject_to_initiator',
    return_targets: options.returnTargets ?? null,
    timeout_hours: null,
    opinion_required: options.opinionRequired ?? false,
    attachment_required: false,
    fields_permission: {
      base: options.base ?? 'readonly',
      partitions: {},
      overrides: options.overrides ?? {},
      conditional_overrides: [],
    },
  }
}

function definition(steps: Array<Record<string, unknown>>): Record<string, unknown> {
  return {
    model_version: 1,
    start: { id: 'start', name: '开始', type: 'start', fields_permission: null },
    steps,
    end: { id: 'end', name: '结束', type: 'end' },
  }
}

export function sequentialDefinition(
  approvals: Array<{ id: string; name: string; userId: number }>,
): Record<string, unknown> {
  return definition(approvals.map((item) => approvalNode(item.id, item.name, item.userId)))
}

export function parallelDefinition(
  mode: 'all' | 'any',
  members: Array<{ id: string; name: string; userId: number }>,
): Record<string, unknown> {
  return definition([
    {
      id: 'p1',
      name: mode === 'all' ? '会签' : '或签',
      type: 'parallel',
      mode,
      members: members.map((item) => approvalNode(item.id, item.name, item.userId)),
    },
  ])
}

/** 先 A 审批，再按金额分流：超过阈值走 B，否则直接结束。 */
export function conditionDefinition(
  threshold: number,
  firstUserId: number,
  branchUserId: number,
): Record<string, unknown> {
  return definition([
    approvalNode('a1', '初审', firstUserId),
    {
      id: 'c1',
      name: '按金额分流',
      type: 'condition',
      branches: [
        {
          id: 'big',
          when: { op: 'and', conditions: [{ field: 'amount', cmp: '>', value: threshold }] },
          steps: [approvalNode('a2', '大额复核', branchUserId)],
        },
        { id: 'small', when: null, steps: [] },
      ],
    },
  ])
}

/** A → B，B 可退回 A。 */
export function returnDefinition(firstUserId: number, secondUserId: number): Record<string, unknown> {
  return definition([
    approvalNode('a1', '退回目标审批', firstUserId),
    approvalNode('a2', '复核审批', secondUserId, { returnTargets: ['a1'] }),
  ])
}

export async function createFlowAndPublish(
  formTemplateId: number,
  name: string,
  flowDefinition: Record<string, unknown>,
): Promise<{ id: number; name: string }> {
  const api = await apiAs('admin')
  try {
    const created = await api.post('flow-templates', {
      data: {
        name,
        code: uniqueCode('E2E_FLOW'),
        form_template_id: formTemplateId,
        initiator_scope: { type: 'all' },
      },
    })
    expect(created.ok()).toBeTruthy()
    const flow = (await created.json()) as { id: number; name: string }

    const versions = await api.get(`flow-templates/${flow.id}/versions`)
    expect(versions.ok()).toBeTruthy()
    const draft = ((await versions.json()) as Array<{ id: number; status: string }>).find(
      (item) => item.status === 'DRAFT',
    )
    if (!draft) throw new Error('新建流程没有草稿版本')

    const saved = await api.put(`flow-versions/${draft.id}`, {
      data: { definition: flowDefinition },
    })
    expect(saved.ok()).toBeTruthy()

    const published = await api.post(`flow-versions/${draft.id}/publish`, {
      data: { remark: 'E2E 自动发布' },
    })
    expect(published.ok()).toBeTruthy()
    return flow
  } finally {
    await api.dispose()
  }
}

// --------------------------------------------------------------------------- 实例

export interface Assignment {
  assignment_id: number
  instance_id: number
  node_name?: string
  node_type?: string
}

export async function submitFor(
  role: Role,
  flowTemplateId: number,
  data: Record<string, unknown>,
): Promise<InstanceBrief> {
  const api = await apiAs(role)
  try {
    const draft = await api.post('instances/drafts', {
      data: { flow_template_id: flowTemplateId, data },
    })
    expect(draft.ok()).toBeTruthy()
    const created = (await draft.json()) as { id: number }

    const submitted = await api.post(`instances/${created.id}/submit`, {
      data: { data, note: '', attachment_ids: [], assignee_picks: {} },
    })
    expect(submitted.ok()).toBeTruthy()
    const body = (await submitted.json()) as InstanceBrief
    return { ...body, id: body.id ?? created.id }
  } finally {
    await api.dispose()
  }
}

export async function findAssignment(role: Role, instanceId: number): Promise<Assignment> {
  const api = await apiAs(role)
  try {
    const response = await api.get('tasks/todo?size=100')
    expect(response.ok()).toBeTruthy()
    const items = ((await response.json()) as { items: Assignment[] }).items
    const hit = items.find((item) => item.instance_id === instanceId)
    if (!hit) throw new Error(`${role} 没有实例 ${instanceId} 的待办`)
    return hit
  } finally {
    await api.dispose()
  }
}

export async function actAs(
  role: Role,
  assignmentId: number,
  action: 'AGREE' | 'REJECT' | 'RETURN' | 'SUBMIT',
  options: {
    opinion?: string
    returnTarget?: string
    fieldPatch?: Record<string, unknown>
  } = {},
): Promise<void> {
  const api = await apiAs(role)
  try {
    const response = await api.post(`tasks/assignments/${assignmentId}/act`, {
      data: {
        action,
        opinion: options.opinion ?? '',
        attachment_ids: [],
        field_patch: options.fieldPatch ?? {},
        return_target: options.returnTarget ?? null,
      },
    })
    expect(response.ok()).toBeTruthy()
  } finally {
    await api.dispose()
  }
}

/** 用接口把待办处理掉，给纯界面用例准备前置状态。 */
export async function approveViaApi(role: Role, instanceId: number, opinion = '同意'): Promise<void> {
  const assignment = await findAssignment(role, instanceId)
  await actAs(role, assignment.assignment_id, 'AGREE', { opinion })
}

export async function todoInstanceIds(role: Role): Promise<number[]> {
  const api = await apiAs(role)
  try {
    const response = await api.get('tasks/todo?size=100')
    expect(response.ok()).toBeTruthy()
    const items = ((await response.json()) as { items: Assignment[] }).items
    return items.map((item) => item.instance_id)
  } finally {
    await api.dispose()
  }
}

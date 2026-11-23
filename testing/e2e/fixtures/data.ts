import type { APIRequestContext } from '@playwright/test'

import { apiAs, type Role } from './auth'

/** 与 backend/app/seeds/sample_flows.py 保持一致。 */
export const LEAVE_FLOW_CODE = 'SAMPLE_LEAVE_FLOW'

export interface InstanceBrief {
  id: number
  code: string
  title: string
  status: string
}

export interface RenderResult {
  instance: {
    id: number
    code: string
    title: string
    status: string
    round: number
    initiator_name: string
  }
  values: Record<string, unknown>
  actions: Array<{ action: string; opinion?: string | null; actor_name?: string }>
  allowed_actions: string[]
}

/** 同一轮 E2E 里唯一，便于在列表/搜索中定位自己造的数据。 */
export function uniqueReason(prefix: string): string {
  return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 1000)}`
}

/** 请假表单的必填数据；默认当天，走「<=3 天」短分支，只经直属上级。 */
export function leaveData(reason: string): Record<string, unknown> {
  return {
    leaveType: 'annual',
    startDate: '2026-11-20',
    endDate: '2026-11-20',
    reason,
  }
}

async function findLeaveFlow(api: APIRequestContext): Promise<{ id: number; name: string }> {
  // 发起人没有设计者权限，不能查 /flow-templates；用与发起中心同一个接口。
  const response = await api.get('instances/available-flows')
  if (!response.ok()) {
    throw new Error(`查询可发起流程失败：${response.status()} ${await response.text()}`)
  }
  const flows = (await response.json()) as Array<{ id: number; name: string; code?: string }>
  const flow = flows.find((item) => item.code === LEAVE_FLOW_CODE)
  if (!flow) {
    throw new Error(`示例流程未找到：${LEAVE_FLOW_CODE}（E2E 库是否已 reset？）`)
  }
  return flow
}

/**
 * 用真实接口造一条「张三已提交」的请假实例。
 *
 * 审批人/驳回重提这类旅程只验证浏览器交互，前置状态用 API 准备，
 * 避免每条用例都从设计表单开始、把失败点混在一起。
 */
export async function submitLeaveAsZhangsan(reason: string): Promise<InstanceBrief> {
  const api = await apiAs('zhangsan')
  try {
    const flow = await findLeaveFlow(api)
    const data = leaveData(reason)

    const created = await api.post('instances/drafts', {
      data: { flow_template_id: flow.id, data },
    })
    if (!created.ok()) {
      throw new Error(`创建草稿失败：${created.status()} ${await created.text()}`)
    }
    const draft = (await created.json()) as { id: number }

    const submitted = await api.post(`instances/${draft.id}/submit`, {
      data: {
        data,
        note: '',
        attachment_ids: [],
        assignee_picks: {},
      },
    })
    if (!submitted.ok()) {
      throw new Error(`提交失败：${submitted.status()} ${await submitted.text()}`)
    }
    const body = (await submitted.json()) as InstanceBrief
    return {
      id: body.id ?? draft.id,
      code: body.code,
      title: body.title,
      status: body.status,
    }
  } finally {
    await api.dispose()
  }
}

/** 以指定角色读实例渲染结果，用于断言后端副作用。 */
export async function renderAs(
  role: Role,
  instanceId: number,
  assignmentId?: number,
): Promise<RenderResult> {
  const api = await apiAs(role)
  try {
    const response = await api.get(`instances/${instanceId}/render`, {
      params: assignmentId ? { assignment_id: assignmentId } : undefined,
    })
    if (!response.ok()) {
      throw new Error(`读取实例失败：${response.status()} ${await response.text()}`)
    }
    return (await response.json()) as RenderResult
  } finally {
    await api.dispose()
  }
}

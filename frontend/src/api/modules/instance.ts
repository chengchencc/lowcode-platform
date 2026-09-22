import { request } from '@/api/http'
import type { OkResp, Page } from '@/types/api'
import type { FlowTemplate } from '@/types/flow'
import type {
  ActPayload,
  InstanceItem,
  InstanceRender,
  NotificationItem,
  StartOptions,
  SubmitPayload,
  TaskRow,
  TodoSummary,
} from '@/types/instance'

export interface InstanceListQuery {
  page?: number
  size?: number
  scope?: 'mine' | 'related' | 'all'
  status?: string
  flow_template_id?: number
  keyword?: string
}

export interface TaskListQuery {
  page?: number
  size?: number
  keyword?: string
  flow_template_id?: number
  unread_only?: boolean
}

export const instanceApi = {
  /** 发起中心：我能发起的流程 */
  availableFlows() {
    return request.get<FlowTemplate[]>('/instances/available-flows')
  },

  /** 发起页元数据：表单 schema + 发起节点权限 + 需指定审批人的节点 */
  startOptions(flowTemplateId: number) {
    return request.get<StartOptions>(`/instances/start-options/${flowTemplateId}`)
  },

  // ---- 草稿 ----
  createDraft(payload: { flow_template_id: number; title?: string | null; data?: object }) {
    return request.post<InstanceItem>('/instances/drafts', payload)
  },

  listDrafts() {
    return request.get<InstanceItem[]>('/instances/drafts')
  },

  updateDraft(id: number, payload: { title?: string | null; data?: object }) {
    return request.put<InstanceItem>(`/instances/${id}/draft`, payload)
  },

  deleteDraft(id: number) {
    return request.delete<OkResp>(`/instances/${id}`)
  },

  // ---- 提交 ----
  submit(id: number, payload: SubmitPayload) {
    return request.post<InstanceItem>(`/instances/${id}/submit`, payload)
  },

  resubmit(id: number, payload: SubmitPayload) {
    return request.post<InstanceItem>(`/instances/${id}/resubmit`, payload)
  },

  // ---- 详情 ----
  /** ★ 详情页一次取全：进度 + 分区权限 + 时间线 + 可执行动作 */
  render(id: number, params?: { assignment_id?: number; snapshot_id?: number }) {
    return request.get<InstanceRender>(`/instances/${id}/render`, { params })
  },

  timeline(id: number) {
    return request.get<InstanceItem[]>(`/instances/${id}/timeline`)
  },

  snapshotDiff(id: number, fromId: number, toId: number) {
    return request.get<Array<{ key: string; old: unknown; new: unknown }>>(
      `/instances/${id}/snapshots/diff`,
      { params: { from: fromId, to: toId } },
    )
  },

  list(params: InstanceListQuery) {
    return request.get<Page<InstanceItem>>('/instances', { params })
  },

  // ---- 实例级操作 ----
  withdraw(id: number, reason?: string | null) {
    return request.post<InstanceItem>(`/instances/${id}/withdraw`, { reason })
  },

  abandon(id: number) {
    return request.post<InstanceItem>(`/instances/${id}/abandon`)
  },

  terminate(id: number, reason: string) {
    return request.post<InstanceItem>(`/instances/${id}/terminate`, { reason })
  },
}

export const taskApi = {
  todo(params: TaskListQuery) {
    return request.get<Page<TaskRow>>('/tasks/todo', { params })
  },

  done(params: TaskListQuery) {
    return request.get<Page<TaskRow>>('/tasks/done', { params })
  },

  cc(params: TaskListQuery) {
    return request.get<Page<TaskRow>>('/tasks/cc', { params })
  },

  mine(params: TaskListQuery & { status?: string }) {
    return request.get<Page<InstanceItem>>('/tasks/mine', { params })
  },

  /** 角标计数（F7.2：前端 ≤10s 轮询它） */
  summary() {
    return request.get<TodoSummary>('/tasks/summary')
  },

  getAssignment(assignmentId: number) {
    return request.get<TaskRow>(`/tasks/assignments/${assignmentId}`)
  },

  returnTargets(assignmentId: number) {
    return request.get<Array<{ node_id: string; name: string; type: string }>>(
      `/tasks/assignments/${assignmentId}/return-targets`,
    )
  },

  /**
   * ★ 处理任务。写操作自动带 `X-Request-Id`（见 api/http.ts），
   * 后端据此保证网络重放不会产生重复动作。
   */
  act(assignmentId: number, payload: ActPayload) {
    return request.post<InstanceItem>(`/tasks/assignments/${assignmentId}/act`, payload)
  },

  markRead(assignmentId: number) {
    return request.post<OkResp>(`/tasks/assignments/${assignmentId}/read`)
  },
}

export const notificationApi = {
  list(params: { page?: number; size?: number; unread_only?: boolean; type?: string }) {
    return request.get<Page<NotificationItem>>('/notifications', { params })
  },

  unreadCount() {
    return request.get<{ count: number }>('/notifications/unread-count', { silent: true })
  },

  markRead(id: number) {
    return request.post<OkResp>(`/notifications/${id}/read`)
  },

  markManyRead(ids: number[]) {
    return request.post<OkResp>('/notifications/read', { ids })
  },

  markAllRead() {
    return request.post<OkResp>('/notifications/read-all')
  },
}

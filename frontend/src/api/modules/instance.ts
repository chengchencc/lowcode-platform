import { request } from '@/api/http'
import type { OkResp, Page } from '@/types/api'
import type { FlowTemplate } from '@/types/flow'
import type {
  ActPayload,
  ExtFieldPayload,
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

export interface ArchiveQuery {
  page?: number
  size?: number
  /** 逗号分隔，默认 APPROVED */
  status?: string
  flow_template_id?: number
  initiator_id?: number
  keyword?: string
  finished_from?: string
  finished_to?: string
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

  // ---- 归档检索与导出（F8）----
  /** 归档列表（默认只看已通过；管理员专属） */
  archive(params: ArchiveQuery) {
    return request.get<Page<InstanceItem>>('/instances/archive', { params })
  },

  /** 导出归档 CSV。返回下载地址，交给 `utils/download.ts` 带 token 取回 */
  archiveExportUrl(params: ArchiveQuery) {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
    }
    const suffix = query.toString()
    return `/instances/archive/export${suffix ? `?${suffix}` : ''}`
  },

  /** 导出单个实例 */
  instanceExportUrl(id: number) {
    return `/instances/${id}/export`
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

  // ---- 机制 C：运行中追加字段（管理员/设计者）----
  /** 追加字段；返回**刷新后的详情页数据**，前端一次请求即可重绘 */
  addExtField(id: number, payload: ExtFieldPayload) {
    return request.post<InstanceRender>(`/instances/${id}/ext-fields`, payload)
  },

  /** 停用（不可物理删除 —— 历史快照里还有它的值） */
  disableExtField(id: number, fieldKey: string) {
    return request.post<InstanceRender>(`/instances/${id}/ext-fields/${fieldKey}/disable`)
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

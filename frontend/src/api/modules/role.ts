import { request } from '@/api/http'
import type { OkResp, Page } from '@/types/api'
import type { DeptMember, Role, RoleInput } from '@/types/org'

export interface AuditLogItem {
  id: number
  actor_id: number | null
  actor_name: string | null
  biz_type: string
  biz_id: number
  action: string
  summary: string | null
  detail: Record<string, unknown> | null
  ip: string | null
  created_at: string
}

export const roleApi = {
  list(params?: { keyword?: string; status?: string }) {
    return request.get<Role[]>('/roles', { params })
  },

  get(id: number) {
    return request.get<Role>(`/roles/${id}`)
  },

  create(payload: RoleInput) {
    return request.post<Role>('/roles', payload)
  },

  update(id: number, payload: Partial<RoleInput>) {
    return request.put<Role>(`/roles/${id}`, payload)
  },

  remove(id: number) {
    return request.delete<OkResp>(`/roles/${id}`)
  },

  members(id: number) {
    return request.get<DeptMember[]>(`/roles/${id}/members`)
  },

  setMembers(id: number, userIds: number[]) {
    return request.put<OkResp>(`/roles/${id}/members`, { user_ids: userIds })
  },
}

export const auditApi = {
  list(params: { page?: number; size?: number; biz_type?: string; actor_id?: number }) {
    return request.get<Page<AuditLogItem>>('/admin/audit-logs', { params })
  },
}

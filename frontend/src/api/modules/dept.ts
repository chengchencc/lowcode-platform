import { request } from '@/api/http'
import type { OkResp } from '@/types/api'
import type { DeptBrief, DeptInput, DeptMember, DeptNode } from '@/types/org'

export const deptApi = {
  tree(includeDisabled = true) {
    return request.get<DeptNode[]>('/departments/tree', {
      params: { include_disabled: includeDisabled },
    })
  },

  options() {
    return request.get<DeptBrief[]>('/departments/options')
  },

  get(id: number) {
    return request.get<DeptNode>(`/departments/${id}`)
  },

  create(payload: DeptInput) {
    return request.post<DeptNode>('/departments', payload)
  },

  update(id: number, payload: Partial<DeptInput>) {
    return request.put<DeptNode>(`/departments/${id}`, payload)
  },

  remove(id: number) {
    return request.delete<OkResp>(`/departments/${id}`)
  },

  members(id: number) {
    return request.get<DeptMember[]>(`/departments/${id}/members`)
  },

  setMembers(id: number, userIds: number[]) {
    return request.put<OkResp>(`/departments/${id}/members`, { user_ids: userIds })
  },
}

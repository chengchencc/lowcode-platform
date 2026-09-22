import { request } from '@/api/http'
import type { OkResp, Page } from '@/types/api'
import type { UserInput, UserItem, UserListQuery, UserOption, UserStatus } from '@/types/org'

export const userApi = {
  list(params: UserListQuery) {
    return request.get<Page<UserItem>>('/users', { params })
  },

  get(id: number) {
    return request.get<UserItem>(`/users/${id}`)
  },

  create(payload: UserInput) {
    return request.post<UserItem>('/users', payload)
  },

  update(id: number, payload: UserInput) {
    return request.put<UserItem>(`/users/${id}`, payload)
  },

  remove(id: number) {
    return request.delete<OkResp>(`/users/${id}`)
  },

  resetPassword(id: number, newPassword: string) {
    return request.post<OkResp>(`/users/${id}/reset-password`, { new_password: newPassword })
  },

  setStatus(id: number, status: UserStatus) {
    return request.post<UserItem>(`/users/${id}/status`, { status })
  },

  options(params: { keyword?: string; dept_id?: number | null; limit?: number }) {
    return request.get<UserOption[]>('/users/options', { params })
  },

  importCsv(file: File) {
    const form = new FormData()
    form.append('file', file)
    return request.post<{
      created: number
      failed: Array<{ line: number; username: string; message: string }>
      default_password: string
    }>('/users/import', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

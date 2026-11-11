import type { AxiosResponse } from 'axios'

import { request } from '@/api/http'
import type { OkResp } from '@/types/api'
import type {
  WorkStatImportPreview,
  WorkStatRow,
  WorkStatRowLog,
  WorkStatSheet,
} from '@/types/workStat'

export interface WorkStatSheetPayload {
  name: string
  description?: string | null
  columns: Array<{
    key: string
    label: string
    type: string
    width?: number
    required?: boolean
    options?: string[]
  }>
  viewer_scope?: { roles: string[]; depts: number[]; users: number[] } | null
  editor_scope?: { roles: string[]; depts: number[]; users: number[] } | null
  sort?: number
  status?: 'ACTIVE' | 'DISABLED'
}

function fileForm(file: File): FormData {
  const form = new FormData()
  form.append('file', file)
  return form
}

export const workStatApi = {
  listSheets() {
    return request.get<WorkStatSheet[]>('/work-stat-sheets')
  },

  getSheet(id: number) {
    return request.get<WorkStatSheet>(`/work-stat-sheets/${id}`)
  },

  createSheet(payload: WorkStatSheetPayload) {
    return request.post<WorkStatSheet>('/work-stat-sheets', payload)
  },

  updateSheet(id: number, payload: Partial<WorkStatSheetPayload>) {
    return request.put<WorkStatSheet>(`/work-stat-sheets/${id}`, payload)
  },

  deleteSheet(id: number) {
    return request.delete<OkResp>(`/work-stat-sheets/${id}`)
  },

  rows(id: number, params?: { after_updated_at?: string }) {
    return request.get<WorkStatRow[]>(`/work-stat-sheets/${id}/rows`, { params })
  },

  createRow(id: number, cells: Record<string, unknown>) {
    return request.post<WorkStatRow>(`/work-stat-sheets/${id}/rows`, { cells })
  },

  updateRow(id: number, rowId: number, cells: Record<string, unknown>, version: number) {
    return request.put<WorkStatRow>(`/work-stat-sheets/${id}/rows/${rowId}`, {
      cells,
      version,
    })
  },

  deleteRow(id: number, rowId: number) {
    return request.delete<OkResp>(`/work-stat-sheets/${id}/rows/${rowId}`)
  },

  rowLogs(id: number, rowId: number) {
    return request.get<WorkStatRowLog[]>(`/work-stat-sheets/${id}/rows/${rowId}/logs`)
  },

  importPreview(id: number, file: File) {
    return request.post<WorkStatImportPreview>(
      `/work-stat-sheets/${id}/import`,
      fileForm(file),
      { params: { dry_run: true }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
  },

  importFile(id: number, file: File) {
    return request.post<{ imported: number }>(
      `/work-stat-sheets/${id}/import`,
      fileForm(file),
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  },

  exportFile(id: number) {
    return request.get<AxiosResponse<Blob>>(`/work-stat-sheets/${id}/export`, {
      responseType: 'blob',
      raw: true,
    })
  },
}

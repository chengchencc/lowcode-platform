import { request } from '@/api/http'
import type { OkResp } from '@/types/api'
import type {
  SpreadsheetDetail,
  SpreadsheetScope,
  SpreadsheetState,
  SpreadsheetWorkbook,
} from '@/types/spreadsheet'

export interface SpreadsheetPayload {
  name: string
  description?: string | null
  viewer_scope?: SpreadsheetScope | null
  editor_scope?: SpreadsheetScope | null
}

export const spreadsheetApi = {
  list() {
    return request.get<SpreadsheetWorkbook[]>('/spreadsheet-workbooks')
  },

  create(payload: SpreadsheetPayload) {
    return request.post<SpreadsheetWorkbook>('/spreadsheet-workbooks', payload)
  },

  get(id: number) {
    return request.get<SpreadsheetDetail>(`/spreadsheet-workbooks/${id}`)
  },

  update(id: number, payload: Partial<SpreadsheetPayload>) {
    return request.put<SpreadsheetWorkbook>(`/spreadsheet-workbooks/${id}`, payload)
  },

  save(id: number, snapshot: Record<string, unknown>, version: number) {
    return request.post<{
      version: number
      updated_by: number | null
      updated_by_name: string | null
      updated_at: string | null
    }>(`/spreadsheet-workbooks/${id}/save`, { snapshot, version })
  },

  state(id: number, knownVersion: number) {
    return request.get<SpreadsheetState>(`/spreadsheet-workbooks/${id}/state`, {
      params: { known_version: knownVersion },
      silent: true,
    })
  },

  remove(id: number) {
    return request.delete<OkResp>(`/spreadsheet-workbooks/${id}`)
  },
}

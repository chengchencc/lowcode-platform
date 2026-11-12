/** 共享电子表格工作簿。 */

export interface SpreadsheetScope {
  all: boolean
  roles: string[]
  depts: number[]
  users: number[]
}

export interface SpreadsheetWorkbook {
  id: number
  name: string
  description: string | null
  version: number
  viewer_scope: SpreadsheetScope | null
  editor_scope: SpreadsheetScope | null
  can_edit: boolean
  created_by: number
  created_by_name: string | null
  updated_by: number | null
  updated_by_name: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SpreadsheetDetail extends SpreadsheetWorkbook {
  snapshot: Record<string, unknown> | null
}

export interface SpreadsheetState {
  version: number
  changed: boolean
  snapshot: Record<string, unknown> | null
  updated_by: number | null
  updated_by_name: string | null
  updated_at: string | null
}

/** 工作量统计（M12），与 backend/app/schemas/work_stat.py 对齐。 */

export type WorkStatColumnType = 'text' | 'number' | 'date' | 'select'

export interface WorkStatColumn {
  key: string
  label: string
  type: WorkStatColumnType
  width: number
  required: boolean
  options: string[]
}

export interface WorkStatScope {
  roles: string[]
  depts: number[]
  users: number[]
}

export interface WorkStatSheet {
  id: number
  name: string
  description: string | null
  columns: WorkStatColumn[]
  viewer_scope: WorkStatScope | null
  editor_scope: WorkStatScope | null
  sort: number
  status: 'ACTIVE' | 'DISABLED'
  can_edit: boolean
  created_by: number
  created_at: string | null
  updated_at: string | null
}

export interface WorkStatRow {
  id: number
  row_no: number
  cells: Record<string, unknown>
  version: number
  updated_by: number | null
  updated_at: string | null
}

export interface WorkStatRowLog {
  id: number
  action: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  actor_id: number
  actor_name: string | null
  created_at: string | null
}

export interface WorkStatImportPreview {
  headers: string[]
  preview_rows: Array<Record<string, unknown>>
  warnings: string[]
  total_rows: number
}

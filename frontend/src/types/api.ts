/** 与后端约定的通用类型。全链路 snake_case，与 Python 侧保持一致。 */

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
}

/** 后端统一错误体：{"detail": {"code", "message", "extra"?}} */
export interface ApiErrorDetail {
  code: string
  message: string
  extra?: {
    errors?: Array<{ field: string; message: string }>
    [key: string]: unknown
  }
}

export interface OkResp {
  ok: boolean
  message?: string | null
}

export interface PageQuery {
  page?: number
  size?: number
  keyword?: string
}

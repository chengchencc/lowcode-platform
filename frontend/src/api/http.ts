import axios, {
  type AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import type { ApiErrorDetail } from '@/types/api'
import { feedback } from '@/utils/feedback'

const ACCESS_KEY = 'flowform.access_token'
const REFRESH_KEY = 'flowform.refresh_token'

export const tokenStore = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  save(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear(): void {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/** 归一化后的接口错误。调用方只要 catch 这个类型即可拿到 code / message。 */
export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly extra: ApiErrorDetail['extra']

  constructor(status: number, code: string, message: string, extra?: ApiErrorDetail['extra']) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.extra = extra
  }

  /** 表单校验类错误，可逐字段展示。 */
  get fieldErrors(): Array<{ field: string; message: string }> {
    return this.extra?.errors ?? []
  }
}

export interface RequestConfig extends AxiosRequestConfig {
  /** 关掉自动错误提示（调用方想自己处理时用，例如登录页想在表单里显示错误）。 */
  silent?: boolean
  /** 内部使用：标记这是刷新 token 后的一次重试，避免无限循环。 */
  _retried?: boolean
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '/api/v1',
  timeout: 20000,
  headers: { 'Content-Type': 'application/json' },
})

// --------------------------------------------------------------------------- 未授权回调

let onUnauthorized: (() => void) | null = null

/** 由 auth store 注册，避免 http 层反向依赖 router / store。 */
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn
}

// --------------------------------------------------------------------------- 请求拦截

const MUTATING = new Set(['post', 'put', 'patch', 'delete'])

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.access
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // 写操作自动带上幂等键（决策 D7）。后端把它落到 instance_actions.request_id
  // 的唯一索引上，网络重试就不会产生重复的业务动作。
  const method = (config.method ?? 'get').toLowerCase()
  if (MUTATING.has(method) && !config.headers['X-Request-Id']) {
    config.headers['X-Request-Id'] = crypto.randomUUID()
  }
  return config
})

// --------------------------------------------------------------------------- 刷新 token

let refreshing: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  const refresh = tokenStore.refresh
  if (!refresh) return false
  try {
    // 用裸 axios 而不是 http 实例，避免再进一遍拦截器造成递归
    const { data } = await axios.post(
      `${http.defaults.baseURL}/auth/refresh`,
      { refresh_token: refresh },
      { timeout: 15000 },
    )
    tokenStore.save(data.access_token, data.refresh_token)
    return true
  } catch {
    tokenStore.clear()
    return false
  }
}

/** 并发 401 只触发一次刷新，其余请求等同一个 Promise。 */
function ensureRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = refreshAccessToken().finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

// --------------------------------------------------------------------------- 响应拦截

/** 这些错误码说明登录态已经不可挽回，刷新也没用。 */
const UNRECOVERABLE = new Set([
  'TOKEN_REVOKED',
  'ACCOUNT_DISABLED',
  'USER_NOT_FOUND',
  'TOKEN_INVALID',
  'TOKEN_TYPE_MISMATCH',
])

function toApiError(error: AxiosError): ApiError {
  const status = error.response?.status ?? 0
  const detail = (error.response?.data as { detail?: ApiErrorDetail } | undefined)?.detail

  if (detail && typeof detail === 'object' && 'code' in detail) {
    return new ApiError(status, detail.code, detail.message, detail.extra)
  }
  if (error.code === 'ECONNABORTED') {
    return new ApiError(status, 'TIMEOUT', '请求超时，请检查网络或稍后重试')
  }
  if (!error.response) {
    return new ApiError(0, 'NETWORK_ERROR', '无法连接服务器，请确认后端已启动')
  }
  return new ApiError(status, 'UNKNOWN', error.message || '请求失败')
}

http.interceptors.response.use(
  (response) => response.data,
  async (error: AxiosError) => {
    const config = error.config as RequestConfig | undefined
    const apiError = toApiError(error)

    if (error.response?.status === 401 && config && !config._retried) {
      if (!UNRECOVERABLE.has(apiError.code)) {
        const ok = await ensureRefresh()
        if (ok) {
          config._retried = true
          return http.request(config)
        }
      }
      tokenStore.clear()
      onUnauthorized?.()
    }

    if (!config?.silent) {
      const extra = apiError.fieldErrors
      const text = extra.length
        ? `${apiError.message}：${extra.map((e) => e.message).join('；')}`
        : apiError.message
      feedback.error(text)
    }

    return Promise.reject(apiError)
  },
)

// --------------------------------------------------------------------------- 便捷方法

export const request = {
  get<T>(url: string, config?: RequestConfig): Promise<T> {
    return http.get(url, config) as unknown as Promise<T>
  },
  post<T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return http.post(url, data, config) as unknown as Promise<T>
  },
  put<T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return http.put(url, data, config) as unknown as Promise<T>
  },
  patch<T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return http.patch(url, data, config) as unknown as Promise<T>
  },
  delete<T>(url: string, config?: RequestConfig): Promise<T> {
    return http.delete(url, config) as unknown as Promise<T>
  },
}

export default http

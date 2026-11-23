import {
  request as playwrightRequest,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test'

export const API_BASE = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000/api/v1'

/** 与 testing/acceptance/TEST-DATA.md 保持一致。 */
export const ACCOUNTS = {
  admin: { username: 'admin', password: 'admin123456' },
  zhangsan: { username: 'zhangsan', password: 'demo123456' },
  lisi: { username: 'lisi', password: 'demo123456' },
  wangwu: { username: 'wangwu', password: 'demo123456' },
  zhaoliu: { username: 'zhaoliu', password: 'demo123456' },
} as const

export type Role = keyof typeof ACCOUNTS

export interface LoginResult {
  access_token: string
  refresh_token: string
  user?: Record<string, unknown>
}

/** 同一轮 E2E 内复用 token，避免每条用例重复登录。 */
const loginCache = new Map<Role, Promise<LoginResult>>()

/** API 登录，返回 token。UI 登录只保留一条冒烟用例，其余测试走这里。 */
export function loginViaApi(role: Role): Promise<LoginResult> {
  let pending = loginCache.get(role)
  if (!pending) {
    pending = doLogin(role).catch((error: unknown) => {
      loginCache.delete(role)
      throw error
    })
    loginCache.set(role, pending)
  }
  return pending
}

async function doLogin(role: Role): Promise<LoginResult> {
  const context = await playwrightRequest.newContext()
  try {
    // 用绝对 URL：baseURL 末尾没有斜杠时，相对路径会吃掉 /api/v1。
    const response = await context.post(`${API_BASE}/auth/login`, { data: ACCOUNTS[role] })
    if (!response.ok()) {
      throw new Error(
        `API 登录失败（${role}）：${response.status()} ${await response.text()}`,
      )
    }
    return (await response.json()) as LoginResult
  } finally {
    await context.dispose()
  }
}

/** 带该角色 token 的 API 上下文，用于测试内造数/断言后端副作用。 */
export async function apiAs(role: Role): Promise<APIRequestContext> {
  const { access_token } = await loginViaApi(role)
  return playwrightRequest.newContext({
    baseURL: `${API_BASE}/`,
    extraHTTPHeaders: { Authorization: `Bearer ${access_token}` },
  })
}

/**
 * 打开一个已登录的页面。
 *
 * 用 addInitScript 在应用脚本执行前写入 localStorage —— 与前端
 * `tokenStore` 的 key 一致（frontend/src/api/http.ts）。
 */
export async function openAs(
  browser: Browser,
  role: Role,
): Promise<{ context: BrowserContext; page: Page }> {
  const { access_token, refresh_token } = await loginViaApi(role)
  const context = await browser.newContext()
  await context.addInitScript(
    ({ access, refresh }) => {
      localStorage.setItem('flowform.access_token', access)
      localStorage.setItem('flowform.refresh_token', refresh)
    },
    { access: access_token, refresh: refresh_token },
  )
  const page = await context.newPage()
  return { context, page }
}

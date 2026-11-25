/**
 * 系统名称（决策 12：平台命名可改）。
 *
 * 名称由后端 `APP_NAME` 决定，前端启动时从公开接口 `/meta` 取一次：
 * 登录页、侧边栏、浏览器标题都读同一个响应式值。
 * 取不到时退回默认名并继续启动 —— 后端不可用时该报的错由具体业务请求报，
 * 不能因为改个名字就让登录页卡住。
 */
import { computed, ref } from 'vue'

import { metaApi } from '@/api/modules/meta'

const DEFAULT_APP_NAME = 'FlowForm'

export const appName = ref(DEFAULT_APP_NAME)
export const appVersion = ref('')

/** Logo 方块里的缩写：中文取前两字，拉丁名称取前两个大写字母（FlowForm → FF）。 */
export function brandInitial(name: string): string {
  const text = name.trim()
  if (!text) return 'FF'
  if (/^[一-鿿]/.test(text)) {
    const cjk = text.match(/[一-鿿]/g) ?? []
    return cjk.slice(0, 2).join('')
  }
  const letters = text.match(/[A-Za-z0-9]/g) ?? []
  const capitals = letters.filter((char) => /[A-Z0-9]/.test(char))
  const source = capitals.length >= 2 ? capitals : letters
  return (source.slice(0, 2).join('') || 'FF').toUpperCase()
}

/** 浏览器标题：`页面 · 系统名称`；页面没有标题时只显示系统名称。 */
export function pageTitle(title?: unknown): string {
  return title ? `${String(title)} · ${appName.value}` : appName.value
}

export const appInitial = computed(() => brandInitial(appName.value))

let loaded = false
let inflight: Promise<void> | null = null

/** 只成功取一次；失败后允许下一次导航重试，期间保持默认名。 */
export function loadAppMeta(): Promise<void> {
  if (loaded) return Promise.resolve()
  inflight ??= metaApi
    .get()
    .then((meta) => {
      const name = meta.name?.trim()
      if (name) appName.value = name
      appVersion.value = meta.version ?? ''
      loaded = true
    })
    .catch(() => {
      inflight = null
    })
  return inflight
}

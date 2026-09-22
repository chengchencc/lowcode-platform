import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { authApi } from '@/api/modules/auth'
import { setUnauthorizedHandler, tokenStore } from '@/api/http'
import type { CurrentUser } from '@/types/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const isAdmin = ref(false)
  const isDesigner = ref(false)
  /** 是否已完成一次 /auth/me —— 路由守卫据此判断要不要先拉用户信息 */
  const resolved = ref(false)

  const roleCodes = computed(() => user.value?.roles.map((r) => r.code) ?? [])
  const displayName = computed(() => user.value?.real_name ?? '')

  function clear(): void {
    user.value = null
    isAdmin.value = false
    isDesigner.value = false
    resolved.value = true
    tokenStore.clear()
  }

  async function login(username: string, password: string): Promise<void> {
    const data = await authApi.login(username, password)
    tokenStore.save(data.access_token, data.refresh_token)
    user.value = data.user
    await fetchMe()
  }

  /** 拉取当前用户与权限。token 失效时抛错，由调用方决定跳转。 */
  async function fetchMe(): Promise<void> {
    const me = await authApi.me()
    user.value = me.user
    isAdmin.value = me.is_admin
    isDesigner.value = me.is_designer
    resolved.value = true
  }

  /** 刷新页面后用已有 token 恢复登录态。失败则静默清空。 */
  async function restore(): Promise<void> {
    if (resolved.value) return
    if (!tokenStore.access) {
      resolved.value = true
      return
    }
    try {
      await fetchMe()
    } catch {
      clear()
    }
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      // 后端不可达也要让本地登出成功，否则用户被卡在登录态里
    } finally {
      clear()
    }
  }

  function hasRole(...codes: string[]): boolean {
    return codes.some((c) => roleCodes.value.includes(c))
  }

  // axios 拦截器在 token 彻底失效时回调这里
  setUnauthorizedHandler(() => clear())

  return {
    user,
    isAdmin,
    isDesigner,
    resolved,
    roleCodes,
    displayName,
    login,
    logout,
    fetchMe,
    restore,
    clear,
    hasRole,
  }
})

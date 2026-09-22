import type { App, Directive } from 'vue'

import { useAuthStore } from '@/stores/auth'

/**
 * 按钮级角色控制：`v-permission="'platform_admin'"` 或 `v-permission="['designer','platform_admin']"`。
 *
 * 只是**隐藏**元素，不是安全边界 —— 真正的鉴权在后端。前端用它来避免
 * 让用户看到一个点了必然 403 的按钮。
 */
const permission: Directive<HTMLElement, string | string[]> = {
  mounted(el, binding) {
    const auth = useAuthStore()
    const required = Array.isArray(binding.value) ? binding.value : [binding.value]
    if (!required.length) return
    if (!auth.hasRole(...required) && !auth.isAdmin) {
      el.remove()
    }
  },
}

export function setupDirectives(app: App): void {
  app.directive('permission', permission)
}

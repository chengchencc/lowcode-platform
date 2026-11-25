import type { Router } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { loadAppMeta, pageTitle } from '@/utils/appMeta'

export function setupGuards(router: Router): void {
  router.beforeEach(async (to) => {
    const auth = useAuthStore()

    // 不阻塞导航：名称到达后会由 main.ts 的 watch 重新套用标题
    void loadAppMeta()

    if (to.meta.title) {
      document.title = pageTitle(to.meta.title)
    }

    // 刷新页面后先用已有 token 恢复登录态（只做一次）
    if (!auth.resolved) {
      await auth.restore()
    }

    if (to.name === 'login') {
      return auth.user ? { path: '/' } : true
    }

    if (!auth.user) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    // 角色门槛。is_admin / is_designer 由后端 /auth/me 计算，前端只做导航层拦截，
    // 真正的权限判定始终在后端（前端绕过了也拿不到数据）。
    const needed = new Set<string>(to.meta.roles ?? [])
    for (const record of to.matched) {
      for (const role of record.meta.roles ?? []) needed.add(role)
    }

    const needsAdmin = to.meta.adminOnly || to.matched.some((r) => r.meta.adminOnly)
    const needsDesigner = needed.has('designer')

    if (needsAdmin && !auth.isAdmin) return { name: 'dashboard' }
    if (needsDesigner && !auth.isDesigner) return { name: 'dashboard' }

    return true
  })
}

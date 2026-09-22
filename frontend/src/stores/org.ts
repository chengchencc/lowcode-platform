import { defineStore } from 'pinia'
import { ref } from 'vue'

import { deptApi } from '@/api/modules/dept'
import { roleApi } from '@/api/modules/role'
import { userApi } from '@/api/modules/user'
import type { DeptNode, Role, UserOption } from '@/types/org'

/**
 * 组织数据的共享缓存。
 *
 * 部门树 / 角色列表在多个页面和选择器里都要用（M2 之后的人员、部门控件更是高频），
 * 每次进页面重拉一遍既慢又浪费。这里做一次性加载 + 手动失效。
 */
export const useOrgStore = defineStore('org', () => {
  const deptTree = ref<DeptNode[]>([])
  const roles = ref<Role[]>([])
  const loadingDepts = ref(false)

  let deptPromise: Promise<void> | null = null
  let rolePromise: Promise<void> | null = null

  /** 并发调用只发一次请求。 */
  async function loadDeptTree(force = false): Promise<void> {
    if (!force && deptTree.value.length) return
    if (!force && deptPromise) return deptPromise
    loadingDepts.value = true
    deptPromise = (async () => {
      try {
        deptTree.value = await deptApi.tree()
      } finally {
        loadingDepts.value = false
        deptPromise = null
      }
    })()
    return deptPromise
  }

  async function loadRoles(force = false): Promise<void> {
    if (!force && roles.value.length) return
    if (!force && rolePromise) return rolePromise
    rolePromise = (async () => {
      try {
        roles.value = await roleApi.list()
      } finally {
        rolePromise = null
      }
    })()
    return rolePromise
  }

  function searchUsers(params: { keyword?: string; dept_id?: number | null }): Promise<UserOption[]> {
    return userApi.options({ ...params, limit: 50 })
  }

  /** 组织数据变更后由页面调用，避免展示陈旧数据。 */
  function invalidateDepts(): void {
    deptTree.value = []
    deptPromise = null
  }

  function invalidateRoles(): void {
    roles.value = []
    rolePromise = null
  }

  /** 把树拍平成 [{value,label,depth}]，供 a-tree-select / a-select 使用。 */
  function flatDepts(nodes: DeptNode[] = deptTree.value, depth = 0): Array<{
    value: number
    label: string
    depth: number
  }> {
    const out: Array<{ value: number; label: string; depth: number }> = []
    for (const node of nodes) {
      out.push({ value: node.id, label: node.name, depth })
      out.push(...flatDepts(node.children, depth + 1))
    }
    return out
  }

  return {
    deptTree,
    roles,
    loadingDepts,
    loadDeptTree,
    loadRoles,
    searchUsers,
    invalidateDepts,
    invalidateRoles,
    flatDepts,
  }
})

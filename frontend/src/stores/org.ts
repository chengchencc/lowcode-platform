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

  async function searchUsers(params: {
    keyword?: string
    dept_id?: number | null
  }): Promise<UserOption[]> {
    const list = await userApi.options({ ...params, limit: 50 })
    rememberUsers(list)
    return list
  }

  // ---- id → 名称 ----------------------------------------------------------
  // 人员/部门控件的**只读**态只有 id，必须换成人名/部门名才有意义。
  // 部门树常驻内存；人员则缓存「曾经出现在候选项里的那些人」。
  // 没缓存到的显示 `#id` —— M4 的实例渲染接口会由服务端直接给名字。

  const userNameCache = ref(new Map<number, string>())

  function rememberUsers(users: UserOption[]): void {
    if (!users.length) return
    const next = new Map(userNameCache.value)
    for (const u of users) next.set(u.id, u.real_name)
    userNameCache.value = next
  }

  function userName(id: number): string {
    return userNameCache.value.get(id) ?? `#${id}`
  }

  function deptName(id: number): string {
    const walk = (nodes: DeptNode[]): string | null => {
      for (const node of nodes) {
        if (node.id === id) return node.name
        const hit = walk(node.children)
        if (hit) return hit
      }
      return null
    }
    return walk(deptTree.value) ?? `#${id}`
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
    rememberUsers,
    userName,
    deptName,
    invalidateDepts,
    invalidateRoles,
    flatDepts,
  }
})

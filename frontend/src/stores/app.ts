import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 状态码 → 中文标签 + 徽标色。各页面共用，避免同一份映射散落多处。 */
export const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  ACTIVE: { text: '启用', color: 'green' },
  DISABLED: { text: '停用', color: 'default' },
}

export const AUDIT_ACTION_LABELS: Record<string, string> = {
  CREATE: '新建',
  UPDATE: '修改',
  DELETE: '删除',
  ENABLE: '启用',
  DISABLE: '停用',
  RESET_PASSWORD: '重置密码',
  IMPORT: '导入',
  GRANT_ROLE: '授予角色',
  REVOKE_ROLE: '移除角色',
  PUBLISH: '发布',
}

export const AUDIT_BIZ_LABELS: Record<string, string> = {
  USER: '用户',
  DEPT: '部门',
  ROLE: '角色',
  FORM_TEMPLATE: '表单模板',
  FLOW_TEMPLATE: '流程模板',
  INSTANCE: '流程实例',
}

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return { sidebarCollapsed, toggleSidebar }
})

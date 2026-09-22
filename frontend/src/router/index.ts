import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import DefaultLayout from '@/layouts/DefaultLayout.vue'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** 需要的角色（任一匹配即可）。管理员天然通过。 */
    roles?: string[]
    /** 仅管理员可见 */
    adminOnly?: boolean
    /** 菜单中隐藏 */
    hidden?: boolean
    icon?: string
  }
}

/**
 * 路由表按 PRD §5 的页面信息架构组织。
 * M2–M4 的页面（发起中心 / 工作台 / 表单与流程配置器 / 消息中心）已预留在菜单结构里，
 * 对应路由在各自里程碑补上。
 */
export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', hidden: true },
  },
  {
    path: '/',
    component: DefaultLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '工作台首页', icon: 'dashboard' },
      },
      {
        path: 'start-center',
        name: 'start-center',
        component: () => import('@/views/StartCenterView.vue'),
        meta: { title: '发起中心' },
      },
      {
        // 发起填写页；带 ?draftId= 即草稿续填
        path: 'start/:flowTemplateId',
        name: 'start-form',
        component: () => import('@/views/StartFormView.vue'),
        meta: { title: '发起流程', hidden: true },
      },
      {
        path: 'workbench/:type(todo|done|mine|cc)',
        name: 'workbench',
        component: () => import('@/views/WorkbenchView.vue'),
        meta: { title: '工作台' },
      },
      {
        // 实例详情页是独立整页：进度条 + 分区表单 + 时间线需要横向空间
        path: 'instance/:id',
        name: 'instance-detail',
        component: () => import('@/views/InstanceDetailView.vue'),
        meta: { title: '单据详情', hidden: true },
      },
      {
        path: 'messages',
        name: 'messages',
        component: () => import('@/views/NotificationCenterView.vue'),
        meta: { title: '消息中心' },
      },
      {
        path: 'admin/forms',
        name: 'form-templates',
        component: () => import('@/views/admin/form/FormTemplateListView.vue'),
        meta: { title: '表单模板', roles: ['designer'] },
      },
      {
        // 设计器做成独立整页：配置表单需要横向空间，塞进带侧边栏的布局里太挤
        path: 'admin/forms/:id/design',
        name: 'form-designer',
        component: () => import('@/views/admin/form/FormDesignerView.vue'),
        meta: { title: '表单配置器', roles: ['designer'], hidden: true },
      },
      {
        path: 'admin/flows',
        name: 'flow-templates',
        component: () => import('@/views/admin/flow/FlowTemplateListView.vue'),
        meta: { title: '流程模板', roles: ['designer'] },
      },
      {
        path: 'admin/flows/:id/design',
        name: 'flow-designer',
        component: () => import('@/views/admin/flow/FlowDesignerView.vue'),
        meta: { title: '流程配置器', roles: ['designer'], hidden: true },
      },
      {
        path: 'admin/org/users',
        name: 'org-users',
        component: () => import('@/views/admin/org/UserView.vue'),
        meta: { title: '用户管理', adminOnly: true, icon: 'user' },
      },
      {
        path: 'admin/org/depts',
        name: 'org-depts',
        component: () => import('@/views/admin/org/DeptView.vue'),
        meta: { title: '部门管理', adminOnly: true, icon: 'apartment' },
      },
      {
        path: 'admin/org/roles',
        name: 'org-roles',
        component: () => import('@/views/admin/org/RoleView.vue'),
        meta: { title: '角色管理', adminOnly: true, icon: 'team' },
      },
      {
        path: 'admin/audit',
        name: 'audit',
        component: () => import('@/views/admin/AuditLogView.vue'),
        meta: { title: '操作审计', adminOnly: true, icon: 'audit' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在', hidden: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

export default router

/**
 * 渲染冒烟测试。
 *
 * 存在的理由：M1 曾经整片界面没渲染出来（antd 组件没注册），而
 * `vue-tsc --noEmit` 和 `vite build` **都通过**——模板里未注册的
 * `<a-button>` 会被 Vue 当成未知自定义元素，typecheck 放行、构建放行，
 * 只在浏览器里静默渲染成空标签。
 *
 * 所以这里做两件 typecheck 做不到的事：
 *   1. 真的挂载组件，断言 DOM 里出现了预期的元素；
 *   2. 监听 console.warn，任何 "Failed to resolve component" 都判定失败。
 *
 * 只要往 src 里加了新页面，就在 MOUNTED_VIEWS 里补一行。
 */

import Antd from 'ant-design-vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRouter, createWebHistory, type Router } from 'vue-router'

// ---- 接口全部 mock：这些测试只关心「组件渲染出来了没」，不关心数据 ----

vi.mock('@/api/modules/auth', () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({ access_token: 'a', refresh_token: 'r', expires_at: 0, user: {} }),
    logout: vi.fn().mockResolvedValue({ ok: true }),
    me: vi.fn().mockRejectedValue(new Error('not logged in')),
    changePassword: vi.fn().mockResolvedValue({ ok: true }),
  },
}))

vi.mock('@/api/modules/user', () => ({
  userApi: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 20 }),
    options: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    setStatus: vi.fn(),
    resetPassword: vi.fn(),
    importCsv: vi.fn(),
  },
}))

vi.mock('@/api/modules/dept', () => ({
  deptApi: {
    tree: vi.fn().mockResolvedValue([]),
    options: vi.fn().mockResolvedValue([]),
    members: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    setMembers: vi.fn(),
  },
}))

vi.mock('@/api/modules/role', () => ({
  roleApi: {
    list: vi.fn().mockResolvedValue([]),
    members: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    setMembers: vi.fn(),
  },
  auditApi: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 20 }),
  },
}))

import AuditLogView from '@/views/admin/AuditLogView.vue'
import DeptView from '@/views/admin/org/DeptView.vue'
import RoleView from '@/views/admin/org/RoleView.vue'
import UserView from '@/views/admin/org/UserView.vue'
import DashboardView from '@/views/DashboardView.vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import LoginView from '@/views/LoginView.vue'
import NotFoundView from '@/views/NotFoundView.vue'

const STUB = { template: '<div />' }

function makeRouter(): Router {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: STUB },
      { path: '/login', name: 'login', component: STUB },
      { path: '/admin/org/users', name: 'org-users', component: STUB },
      { path: '/admin/org/depts', name: 'org-depts', component: STUB },
      { path: '/admin/org/roles', name: 'org-roles', component: STUB },
      { path: '/admin/audit', name: 'audit', component: STUB },
    ],
  })
}

/** 收集 Vue 的「组件解析失败」告警 —— 未注册组件的唯一信号。 */
function watchUnresolved() {
  const messages: string[] = []
  const spy = vi.spyOn(console, 'warn').mockImplementation((...args: unknown[]) => {
    const text = args.map(String).join(' ')
    if (text.includes('Failed to resolve component') || text.includes('Failed to resolve directive')) {
      messages.push(text)
    }
  })
  return { messages, restore: () => spy.mockRestore() }
}

async function mountView(component: unknown) {
  const router = makeRouter()
  await router.push('/')
  await router.isReady()
  return mount(component as never, {
    global: { plugins: [createPinia(), router, Antd] },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

/** 所有需要挂载一遍的页面。新增页面请补进这里。 */
const MOUNTED_VIEWS: Array<[string, unknown]> = [
  ['LoginView', LoginView],
  ['DashboardView', DashboardView],
  ['NotFoundView', NotFoundView],
  ['DefaultLayout', DefaultLayout],
  ['UserView', UserView],
  ['DeptView', DeptView],
  ['RoleView', RoleView],
  ['AuditLogView', AuditLogView],
]

describe('所有页面都能渲染且没有未注册的组件', () => {
  for (const [name, component] of MOUNTED_VIEWS) {
    it(`${name} 挂载无 "Failed to resolve component" 告警`, async () => {
      const { messages, restore } = watchUnresolved()
      try {
        const wrapper = await mountView(component)
        expect(wrapper.html()).not.toBe('')
        expect(messages, `未注册的组件/指令：\n${messages.join('\n')}`).toEqual([])
        wrapper.unmount()
      } finally {
        restore()
      }
    })
  }
})

describe('LoginView 渲染出可交互的登录表单', () => {
  // M1 就是在这里出的问题：整个表单渲染成空标签，页面上只剩「登录」两个字
  it('有用户名输入框、密码输入框和提交按钮', async () => {
    const wrapper = await mountView(LoginView)

    const inputs = wrapper.findAll('input')
    expect(inputs.length, '应至少有用户名和密码两个 input').toBeGreaterThanOrEqual(2)

    const password = wrapper.find('input[type="password"]')
    expect(password.exists(), '密码框应为 type=password').toBe(true)

    const placeholders = inputs.map((i) => i.attributes('placeholder'))
    expect(placeholders).toContain('请输入用户名')
    expect(placeholders).toContain('请输入密码')

    // 真按钮而不是渲染成纯文本
    const button = wrapper.find('button.ant-btn')
    expect(button.exists(), '提交按钮应是 antd 按钮而非裸标签').toBe(true)
    // antd 会在两个中文字符之间插入空格（ant-btn 的 insertSpace），比较时去掉空白
    expect(button.text().replace(/\s/g, '')).toContain('登录')

    wrapper.unmount()
  })

  it('渲染 antd 的表单项结构（label 与控件）', async () => {
    const wrapper = await mountView(LoginView)
    expect(wrapper.findAll('.ant-form-item').length).toBeGreaterThanOrEqual(2)
    expect(wrapper.find('.ant-input').exists()).toBe(true)
    wrapper.unmount()
  })
})

describe('布局与 antd 上下文', () => {
  it('DefaultLayout 渲染出侧边菜单', async () => {
    const wrapper = await mountView(DefaultLayout)
    expect(wrapper.find('.ant-menu').exists(), '侧边菜单应渲染为 antd Menu').toBe(true)
    expect(wrapper.find('.ant-layout').exists(), '外层应是 antd Layout').toBe(true)
    wrapper.unmount()
  })
})

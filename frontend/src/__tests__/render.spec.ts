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

import { FormRenderer } from '@/components/form-renderer'

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

/** 流程配置器一进来就会拉模板/版本/表单 schema，给一份最小的可用数据。 */
vi.mock('@/api/modules/flow', () => {
  const definition = {
    model_version: 1,
    start: { id: 'start', type: 'start', name: '发起', fields_permission: null },
    steps: [
      {
        id: 's1', type: 'approval', name: '部门经理审批',
        assignee: { mode: 'SINGLE', sources: [{ type: 'dept_manager' }] },
        reject_policy: 'reject_to_initiator', return_targets: null, timeout_hours: null,
        opinion_required: false, attachment_required: false,
        fields_permission: { base: 'readonly', partitions: {}, overrides: {}, conditional_overrides: [] },
      },
      {
        id: 'c1', type: 'condition', name: '按金额分流',
        branches: [
          { id: 'b1', name: '大额',
            when: { op: 'and', conditions: [{ field: 'amount', cmp: '>', value: 2000 }] },
            steps: [{ id: 's2', type: 'fill', name: '财务补充',
              assignee: { mode: 'SINGLE', sources: [] }, return_targets: null, timeout_hours: null,
              fields_permission: { base: 'hidden', partitions: {}, overrides: {}, conditional_overrides: [] } }] },
          { id: 'else', name: '否则', when: null, steps: [] },
        ],
      },
    ],
    end: { id: 'end', type: 'end', name: '结束' },
  }
  const version = {
    id: 1, template_id: 1, version_no: 1, status: 'DRAFT', remark: null,
    locked_form_version_id: 1, locked_form_version_no: 1,
    created_by: 1, published_at: null, created_at: null,
    definition, validation_report: null,
  }
  return {
    flowApi: {
      listTemplates: vi.fn().mockResolvedValue([]),
      getTemplate: vi.fn().mockResolvedValue({
        id: 1, name: '费用报销流程', code: null, category: null, status: 'DRAFT',
        description: null, form_template_id: 1, form_template_name: '报销单',
        initiator_scope: { type: 'all' },
        current_version_id: null, current_version_no: null,
        locked_form_version_id: null, locked_form_version_no: null,
        draft_version_id: 1, version_count: 1, node_count: 2,
        created_by: 1, created_at: null, updated_at: null,
      }),
      createTemplate: vi.fn(),
      updateTemplate: vi.fn(),
      setTemplateStatus: vi.fn(),
      deleteTemplate: vi.fn(),
      listVersions: vi.fn().mockResolvedValue([]),
      createVersion: vi.fn().mockResolvedValue(version),
      getVersion: vi.fn().mockResolvedValue(version),
      saveVersion: vi.fn().mockResolvedValue(version),
      deleteVersion: vi.fn(),
      validateVersion: vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] }),
      publishVersion: vi.fn().mockResolvedValue(version),
      returnTargets: vi.fn().mockResolvedValue([]),
    },
  }
})

/** 表单配置器一进来就会拉模板与版本，这里给一份最小的可用数据。 */
vi.mock('@/api/modules/form', () => {
  const schema = {
    model_version: 1,
    layout: { label_position: 'top', columns: 2 },
    sections: [
      {
        key: 'sec_apply',
        title: '申请信息',
        stage: 'apply',
        sort: 1,
        fields: [
          { key: 'reason', label: '事由', type: 'text', required: true, visible_at_start: true },
          {
            key: 'items',
            label: '明细',
            type: 'subtable',
            columns: [
              { key: 'name', label: '名称', type: 'text' },
              {
                key: 'amount',
                label: '小计',
                type: 'formula',
                formula: { type: 'arithmetic', expression: '1 + 1' },
              },
            ],
          },
        ],
      },
    ],
  }
  const version = {
    id: 1,
    template_id: 1,
    version_no: 1,
    status: 'DRAFT',
    remark: null,
    created_by: 1,
    published_at: null,
    created_at: null,
    schema_data: schema,
    referenced_by_flows: [],
  }
  return {
    formApi: {
      listTemplates: vi.fn().mockResolvedValue([]),
      groups: vi.fn().mockResolvedValue([]),
      getTemplate: vi.fn().mockResolvedValue({
        id: 1,
        name: '报销单',
        code: null,
        group_name: null,
        icon: null,
        status: 'DRAFT',
        description: null,
        current_version_id: null,
        current_version_no: null,
        draft_version_id: 1,
        version_count: 1,
        field_count: 4,
        created_by: 1,
        created_at: null,
        updated_at: null,
      }),
      createTemplate: vi.fn(),
      updateTemplate: vi.fn(),
      setTemplateStatus: vi.fn(),
      copyTemplate: vi.fn(),
      deleteTemplate: vi.fn(),
      exportTemplate: vi.fn(),
      importTemplate: vi.fn(),
      listVersions: vi.fn().mockResolvedValue([]),
      createVersion: vi.fn().mockResolvedValue(version),
      getVersion: vi.fn().mockResolvedValue(version),
      saveVersion: vi.fn().mockResolvedValue(version),
      deleteVersion: vi.fn(),
      validateVersion: vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] }),
      publishVersion: vi.fn().mockResolvedValue(version),
      previewVersion: vi.fn().mockResolvedValue({
        version_id: 1,
        template_id: 1,
        schema_data: schema,
        sample_data: {},
        computed_fields: [],
      }),
    },
    fileApi: {
      upload: vi.fn(),
      remove: vi.fn(),
      downloadUrl: (id: number) => `/api/v1/files/${id}/download`,
    },
  }
})

import AuditLogView from '@/views/admin/AuditLogView.vue'
import FlowDesignerView from '@/views/admin/flow/FlowDesignerView.vue'
import FlowTemplateListView from '@/views/admin/flow/FlowTemplateListView.vue'
import FormDesignerView from '@/views/admin/form/FormDesignerView.vue'
import FormTemplateListView from '@/views/admin/form/FormTemplateListView.vue'
import DeptView from '@/views/admin/org/DeptView.vue'
import RoleView from '@/views/admin/org/RoleView.vue'
import UserView from '@/views/admin/org/UserView.vue'
import DashboardView from '@/views/DashboardView.vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import LoginView from '@/views/LoginView.vue'
import NotFoundView from '@/views/NotFoundView.vue'

const STUB = { template: '<div />' }

/** 需要带路由参数的页面（设计器读 route.params.id）传 path 进去。 */
function makeRouter(initialPath = '/'): Router {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: STUB },
      { path: '/login', name: 'login', component: STUB },
      { path: '/admin/org/users', name: 'org-users', component: STUB },
      { path: '/admin/org/depts', name: 'org-depts', component: STUB },
      { path: '/admin/org/roles', name: 'org-roles', component: STUB },
      { path: '/admin/audit', name: 'audit', component: STUB },
      { path: '/admin/forms', name: 'form-templates', component: STUB },
      { path: '/admin/forms/:id/design', name: 'form-designer', component: STUB },
      { path: '/admin/flows', name: 'flow-templates', component: STUB },
      { path: '/admin/flows/:id/design', name: 'flow-designer', component: STUB },
      { path: initialPath, name: 'fallback', component: STUB },
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

async function mountView(component: unknown, path = '/') {
  const router = makeRouter(path)
  await router.push(path)
  await router.isReady()
  return mount(component as never, {
    global: { plugins: [createPinia(), router, Antd] },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

/**
 * 所有需要挂载一遍的页面。**新增页面请补进这里** ——
 * 这是唯一能发现「组件没注册 / 页面渲染不出来」的关卡（见文件头说明）。
 * 第三个元素是可选的挂载路径（需要路由参数的页面用）。
 */
const MOUNTED_VIEWS: Array<[string, unknown, string?]> = [
  ['LoginView', LoginView],
  ['DashboardView', DashboardView],
  ['NotFoundView', NotFoundView],
  ['DefaultLayout', DefaultLayout],
  ['UserView', UserView],
  ['DeptView', DeptView],
  ['RoleView', RoleView],
  ['AuditLogView', AuditLogView],
  ['FormTemplateListView', FormTemplateListView],
  ['FormDesignerView', FormDesignerView, '/admin/forms/1/design'],
  ['FlowTemplateListView', FlowTemplateListView],
  ['FlowDesignerView', FlowDesignerView, '/admin/flows/1/design'],
]

describe('所有页面都能渲染且没有未注册的组件', () => {
  for (const [name, component, path] of MOUNTED_VIEWS) {
    it(`${name} 挂载无 "Failed to resolve component" 告警`, async () => {
      const { messages, restore } = watchUnresolved()
      try {
        const wrapper = await mountView(component, path ?? '/')
        expect(wrapper.html()).not.toBe('')
        expect(messages, `未注册的组件/指令：\n${messages.join('\n')}`).toEqual([])
        wrapper.unmount()
      } finally {
        restore()
      }
    })
  }
})

describe('表单渲染器（三态）', () => {
  const schema = {
    model_version: 1,
    sections: [
      {
        key: 'sec_apply',
        title: '申请信息',
        stage: 'apply' as const,
        fields: [
          { key: 'reason', label: '事由', type: 'text' as const, required: true, visible_at_start: true },
          {
            key: 'supplement',
            label: '财务补充金额',
            type: 'number' as const,
            visible_at_start: false,
          },
        ],
      },
      {
        key: 'sec_supplement',
        title: '财务补充',
        stage: 'supplement' as const,
        fields: [
          { key: 'invoiceNo', label: '发票号', type: 'text' as const, visible_at_start: false },
        ],
      },
    ],
  }

  it('编辑态下 visible_at_start=false 的字段不渲染', async () => {
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const wrapper = mount(FormRenderer, {
      props: { schema, modelValue: {}, mode: 'edit' },
      global: { plugins: [createPinia(), router, Antd] },
    })
    expect(wrapper.text()).toContain('事由')
    // 「财务补充金额」在申请区且标记为发起隐藏 → 不该出现
    expect(wrapper.text()).not.toContain('财务补充金额')
    // 整个「财务补充」分区里只有一个隐藏字段 → 整块不渲染（机制 B）
    expect(wrapper.text()).not.toContain('发票号')
    wrapper.unmount()
  })

  it('只读态下所有字段都渲染且没有输入框', async () => {
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const wrapper = mount(FormRenderer, {
      props: { schema, modelValue: { reason: '出差', invoiceNo: 'INV-1' }, mode: 'readonly' },
      global: { plugins: [createPinia(), router, Antd] },
    })
    expect(wrapper.text()).toContain('事由')
    expect(wrapper.text()).toContain('发票号')
    expect(wrapper.text()).toContain('INV-1')
    expect(wrapper.findAll('input').length).toBe(0)
    wrapper.unmount()
  })
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

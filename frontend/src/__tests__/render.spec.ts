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
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRouter, createWebHistory, type Router } from 'vue-router'

import { FormRenderer } from '@/components/form-renderer'
import { useAuthStore } from '@/stores/auth'
// 真实路由表：菜单跳转的 bug 只有用它才测得出来（测试里的 STUB 路由是自己写的）
import { routes as realRoutes } from '@/router'
import { instanceApi } from '@/api/modules/instance'
import type { ActionEntry, InstanceRender } from '@/types/instance'
import { Menu } from 'ant-design-vue'

/** 用**真实路由表**建路由：菜单跳转类的问题只有用它才测得出来 */
function makeRealRouter(): Router {
  return createRouter({ history: createWebHistory(), routes: realRoutes })
}

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

/** M4：发起与工作台。详情页一次取全，所以 mock 也要给全。 */
vi.mock('@/api/modules/instance', () => {
  const instance = {
    id: 1, code: 'LX20260922-0001', title: '请假 5 天', status: 'RUNNING', round: 1,
    flow_template_id: 1, flow_template_name: '请假申请', flow_version_id: 1, form_version_id: 1,
    initiator_id: 1, initiator_name: '张三', initiator_dept_name: '技术部',
    current_node_keys: ['直属上级审批'], abnormal: false,
    pending_count: 1, done_count: 1, my_pending_count: 1,
    created_at: null, started_at: null, finished_at: null, last_action_at: null,
    terminated_reason: null,
  }
  const render = {
    instance,
    my_role: 'CURRENT_HANDLER',
    assignment: { assignment_id: 1, task_id: 1, user_id: 1, status: 'PENDING', seq: 0, acted_at: null },
    current_node: {
      node_id: 's1', name: '直属上级审批', type: 'approval', type_label: '审批',
      assignee_mode: 'SINGLE', opinion_required: false, attachment_required: false,
    },
    schema_data: { sections: [{ key: 's', title: '申请信息', stage: 'apply', fields: [
      { key: 'reason', label: '事由', type: 'text' },
    ] }] },
    values: { reason: '旅行' },
    permissions: { reason: { visible: true, editable: false, required: false, reason: 'L0' } },
    progress: [
      { node_id: 's1', name: '直属上级审批', type: 'approval', type_label: '审批',
        status: 'ACTIVE', assignees: [], activation_seq: 1 },
      { node_id: 'c1', name: '按天数分流', type: 'condition', type_label: '条件分支',
        branches: [{ branch_id: 'b1', name: '长假', is_else: false, taken: false, nodes: [] }] },
      { node_id: 'p1', name: '财务双签', type: 'parallel', type_label: '并行', mode: 'all',
        status: 'PENDING', members: [
          { node_id: 'm1', name: '会计审批', type: 'approval', type_label: '审批', status: 'PENDING' },
        ] },
    ],
    actions: [
      { action_id: 1, action: 'SUBMIT', action_label: '提交', node_key: null, node_name: null,
        actor_id: 1, actor_name: '张三', opinion: null, round: 1, from_status: 'DRAFT',
        to_status: 'RUNNING', changed_fields: [], attachments: [], snapshot_id: 1,
        snapshot_seq: 1, created_at: '2026-09-22T10:00:00' },
    ],
    allowed_actions: ['AGREE', 'REJECT', 'RETURN'],
    return_targets: [],
    attachments: [],
    snapshot: null,
    ext_fields: [],
  }
  const emptyPage = { items: [], total: 0, page: 1, size: 20 }
  return {
    instanceApi: {
      availableFlows: vi.fn().mockResolvedValue([]),
      startOptions: vi.fn().mockResolvedValue({
        flow_template_id: 1, flow_template_name: '请假申请',
        flow_version_id: 1, flow_version_no: 1, form_version_id: 1, form_version_no: 1,
        schema_data: { sections: [{ key: 's', title: '申请信息', stage: 'apply', fields: [
          { key: 'reason', label: '事由', type: 'text', required: true },
        ] }] },
        permissions: { reason: { visible: true, editable: true, required: true, reason: 'L0' } },
        initiator_select_nodes: [], nodes: [],
      }),
      createDraft: vi.fn().mockResolvedValue(instance),
      listDrafts: vi.fn().mockResolvedValue([]),
      updateDraft: vi.fn().mockResolvedValue(instance),
      deleteDraft: vi.fn(),
      submit: vi.fn().mockResolvedValue(instance),
      resubmit: vi.fn().mockResolvedValue(instance),
      render: vi.fn().mockResolvedValue(render),
      timeline: vi.fn().mockResolvedValue([]),
      snapshotDiff: vi.fn().mockResolvedValue([]),
      list: vi.fn().mockResolvedValue(emptyPage),
      withdraw: vi.fn(), abandon: vi.fn(), terminate: vi.fn(),
      archive: vi.fn().mockResolvedValue(emptyPage),
      archiveExportUrl: vi.fn().mockReturnValue('/api/v1/instances/archive/export'),
      instanceExportUrl: vi.fn().mockReturnValue('/api/v1/instances/1/export'),
      addExtField: vi.fn().mockResolvedValue(render),
      disableExtField: vi.fn().mockResolvedValue(render),
    },
    taskApi: {
      todo: vi.fn().mockResolvedValue(emptyPage),
      done: vi.fn().mockResolvedValue(emptyPage),
      cc: vi.fn().mockResolvedValue(emptyPage),
      mine: vi.fn().mockResolvedValue(emptyPage),
      summary: vi.fn().mockResolvedValue({ todo: 2, cc_unread: 1, mine_running: 0 }),
      getAssignment: vi.fn(), returnTargets: vi.fn().mockResolvedValue([]),
      act: vi.fn(), markRead: vi.fn(),
    },
    notificationApi: {
      list: vi.fn().mockResolvedValue(emptyPage),
      unreadCount: vi.fn().mockResolvedValue({ count: 0 }),
      markRead: vi.fn(), markManyRead: vi.fn(), markAllRead: vi.fn(),
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
import InstanceArchiveView from '@/views/admin/InstanceArchiveView.vue'
import FlowDesignerView from '@/views/admin/flow/FlowDesignerView.vue'
import FlowTemplateListView from '@/views/admin/flow/FlowTemplateListView.vue'
import FormDesignerView from '@/views/admin/form/FormDesignerView.vue'
import FormTemplateListView from '@/views/admin/form/FormTemplateListView.vue'
import InstanceDetailView from '@/views/InstanceDetailView.vue'
import NotificationCenterView from '@/views/NotificationCenterView.vue'
import StartCenterView from '@/views/StartCenterView.vue'
import StartFormView from '@/views/StartFormView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import DeptView from '@/views/admin/org/DeptView.vue'
import RoleView from '@/views/admin/org/RoleView.vue'
import UserView from '@/views/admin/org/UserView.vue'
import DashboardView from '@/views/DashboardView.vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { MENU_DEFAULT_PARAMS, buildMenuItems, leafKeys } from '@/layouts/menu'
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
      { path: '/admin/instances', name: 'instances', component: STUB },
      { path: '/admin/forms', name: 'form-templates', component: STUB },
      { path: '/admin/forms/:id/design', name: 'form-designer', component: STUB },
      { path: '/admin/flows', name: 'flow-templates', component: STUB },
      { path: '/admin/flows/:id/design', name: 'flow-designer', component: STUB },
      { path: '/start-center', name: 'start-center', component: STUB },
      { path: '/start/:flowTemplateId', name: 'start-form', component: STUB },
      { path: '/workbench/:type', name: 'workbench', component: STUB },
      { path: '/instance/:id', name: 'instance-detail', component: STUB },
      { path: '/messages', name: 'messages', component: STUB },
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
  ['StartCenterView', StartCenterView],
  ['StartFormView', StartFormView, '/start/1'],
  ['WorkbenchView', WorkbenchView, '/workbench/todo'],
  ['InstanceDetailView', InstanceDetailView, '/instance/1'],
  ['NotificationCenterView', NotificationCenterView],
  ['InstanceArchiveView', InstanceArchiveView, '/admin/instances'],
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


describe('画布节点按钮（完整设计器集成）', () => {
  it('条件分支内的节点可以选中并在右侧面板配置', async () => {
    const wrapper = await mountView(FlowDesignerView, '/admin/flows/1/design')
    await flushPromises()

    await wrapper.find('[data-node-id="s2"]').trigger('click')
    await flushPromises()

    expect(
      wrapper.text(),
      '点击分支内节点后，右侧属性面板应切换到该节点',
    ).toContain('节点属性：财务补充')
    wrapper.unmount()
  })

  it('审批节点的 + 与删除都能生效', async () => {
    const { messages, restore } = watchUnresolved()
    try {
      vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
      const wrapper = await mountView(FlowDesignerView, '/admin/flows/1/design')
      await flushPromises()

      expect(wrapper.find('[data-node-id="s1"]').exists(), '应渲染审批节点 s1').toBe(true)
      const before = wrapper.findAll('[data-node-id]').length

      await wrapper.find('[data-node-id="s1"] [title="在后面插入节点"]').trigger('click')
      await flushPromises()
      const modalText = document.body.textContent?.replace(/\s+/g, '') ?? ''
      expect(modalText, '点击 + 应打开插入弹窗').toContain('插入节点')

      const option = Array.from(document.body.querySelectorAll('button'))
        .find((button) => button.textContent?.replace(/\s+/g, '') === '审批节点')
      expect(option, '弹窗里应有「审批节点」选项').toBeTruthy()
      option!.click()
      await flushPromises()
      expect(wrapper.findAll('[data-node-id]').length, '插入后节点数应增加').toBe(before + 1)

      await wrapper.find('[data-node-id="s1"] [title="删除节点"]').trigger('click')
      await flushPromises()
      expect(wrapper.find('[data-node-id="s1"]').exists(), '删除后节点应消失').toBe(false)

      expect(messages, `未注册的组件/指令：\n${messages.join('\n')}`).toEqual([])
      wrapper.unmount()
    } finally {
      restore()
    }
  })
})


describe('设计器的发布按钮可用性', () => {
  // 曾经的 bug：发布按钮的禁用条件写成 `readonly || !dirty`，
  // 而设计器有 1.5s 自动保存，保存后 dirty=false → 按钮立刻变灰，
  // 用户配好流程却点不了发布。typecheck 与 build 都不会发现这类问题。
  const CASES: Array<[string, unknown, string]> = [
    ['表单配置器', FormDesignerView, '/admin/forms/1/design'],
    ['流程配置器', FlowDesignerView, '/admin/flows/1/design'],
  ]

  for (const [name, component, path] of CASES) {
    it(`${name}：草稿版本下发布按钮可用`, async () => {
      const wrapper = await mountView(component, path)
      await flushPromises()

      const publish = wrapper
        .findAll('button')
        .find((b) => b.text().replace(/\s/g, '') === '发布')

      expect(publish, `应能找到「发布」按钮`).toBeTruthy()
      expect(
        publish!.attributes('disabled'),
        '草稿状态下发布按钮不应被禁用',
      ).toBeUndefined()

      wrapper.unmount()
    })
  }
})


describe('工作台路由可达性', () => {
  // 曾经的 bug：路由是 `workbench/:type(todo|done|mine|cc)`（type 必填），
  // 而菜单跳转只写了 router.push({name:'workbench'}) —— 缺必填参数时
  // Vue Router **静默中止导航**，用户看到的是「点了没反应」。
  // 用真实路由表验证，而不是测试里另建的 STUB 路由。
  it('直接访问 /workbench 会重定向到「待办」', async () => {
    const router = makeRealRouter()
    await router.push('/workbench')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('workbench')
    expect(router.currentRoute.value.params.type).toBe('todo')
  })

  it('四个 tab 都能抵达', async () => {
    const router = makeRealRouter()
    await router.push('/')
    await router.isReady()

    for (const type of ['todo', 'done', 'mine', 'cc']) {
      await router.push({ name: 'workbench', params: { type } })
      expect(router.currentRoute.value.name, `${type} 应能抵达`).toBe('workbench')
      expect(router.currentRoute.value.params.type).toBe(type)
    }
  })

  it('菜单里的每一项都能解析到路由（列表从菜单结构读，不手维护）', () => {
    // 曾经这里是手写的 MENU_KEYS，结果「实例管理」加进菜单时漏了同步 ——
    // 而 DefaultLayout 那边也有一份手维护的白名单，两边一起漏，点了没反应。
    // 现在菜单结构在 layouts/menu.ts，白名单由路由表推导，这里直接遍历菜单。
    const router = makeRealRouter()
    const keys = leafKeys(buildMenuItems({ isAdmin: true, todoCount: 3, ccUnread: 1 }))

    expect(keys, '菜单里应能找到实例管理').toContain('instances')
    for (const name of keys) {
      const resolved = router.resolve({ name, params: MENU_DEFAULT_PARAMS[name] })
      expect(resolved.matched.length, `${name} 应能解析到路由`).toBeGreaterThan(0)
      // 路径里不应残留未填充的参数（如 /workbench/:type）
      expect(resolved.path, `${name} 的路径不应含未填充参数`).not.toMatch(/:[a-zA-Z]/)
    }
  })
})


describe('菜单点击能真正跳转', () => {
  // 这才是那个 bug 的直接复现：工作台路由的 type 是必填参数，
  // 菜单若 push({name}) 不带参数，Vue Router 会静默中止导航（点了没反应）。
  // 路由表里的 redirect 只对「按 path 访问」生效，救不了按 name 跳转。
  async function mountLayout() {
    const router = makeRealRouter()
    // 先备好登录态再导航：路由守卫在 push 时就会跑，晚一步就会被踹回登录页
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore(pinia)
    // 用管理员挂载：菜单里才会出现实例管理 / 操作审计这些项
    auth.isAdmin = true
    auth.isDesigner = true
    auth.resolved = true
    auth.user = { id: 1, username: 'admin', real_name: '管理员', roles: [] } as never

    await router.push('/')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: { plugins: [pinia, router, Antd] },
    })
    await flushPromises()
    return { router, wrapper }
  }

  it('点击菜单「工作台」落到待办页', async () => {
    const { router, wrapper } = await mountLayout()

    const menu = wrapper.findComponent(Menu)
    expect(menu.exists(), '应能找到侧边菜单').toBe(true)

    menu.vm.$emit('click', { key: 'workbench' })
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('workbench')
    expect(router.currentRoute.value.params.type).toBe('todo')

    wrapper.unmount()
  })

  it('每个菜单项点下去都真的跳转（含实例管理）', async () => {
    // 「实例管理」曾经点了没反应：菜单项加了，但可跳转白名单是手维护的、漏了它。
    // 这里逐个点一遍 —— 任何一项跳不动都会红。
    const { router, wrapper } = await mountLayout()
    const menu = wrapper.findComponent(Menu)
    const keys = leafKeys(buildMenuItems({ isAdmin: true, todoCount: 0, ccUnread: 0 }))

    for (const key of keys) {
      await router.push('/')
      menu.vm.$emit('click', { key })
      await flushPromises()
      expect(router.currentRoute.value.name, `点「${key}」应跳到同名路由`).toBe(key)
    }

    wrapper.unmount()
    // 每个页面都是懒加载的真实组件，10 来个菜单项在默认 5s 里跑不完
  }, 30000)
})


describe('实例详情页版面', () => {
  // 版面要求（用户指定）：
  //   处理按钮 → 标题栏右上角；审批进度 → 表单之后
  // 用 DOM 文本的**先后顺序**断言，而不是找具体选择器 —— 后者会随样式调整碎掉。
  it('处理按钮在表单之前（标题栏里），审批进度在表单之后', async () => {
    const wrapper = await mountView(InstanceDetailView, '/instance/1')
    await flushPromises()

    // 去掉空白再找：antd 的 Button 会在两个中文字符间插入空格（insertSpace），
    // 「同意」在 DOM 里是「同 意」
    const html = wrapper.html().replace(/\s+/g, '')
    const at = (text: string) => html.indexOf(text)

    expect(at('同意'), '应渲染出「同意」按钮').toBeGreaterThan(-1)
    expect(at('申请信息'), '应渲染出表单分区').toBeGreaterThan(-1)
    expect(at('审批进度'), '应渲染出进度卡片').toBeGreaterThan(-1)

    expect(at('同意'), '处理按钮应在表单之前（标题栏）').toBeLessThan(at('申请信息'))
    expect(at('审批进度'), '审批进度应在表单之后').toBeGreaterThan(at('申请信息'))

    wrapper.unmount()
  })
})


describe('机制 C：运行中追加字段', () => {
  // 「追加字段」入口只给管理员/设计者（F5.1）。用 auth store 的角色判断 ——
  // 设计者看自己经手的单子时 my_role 是发起人/处理人，光看 my_role 判断不出来。
  async function mountAs(component: unknown, path: string, isDesigner: boolean) {
    const router = makeRouter(path)
    await router.push(path)
    await router.isReady()
    const pinia = createPinia()
    useAuthStore(pinia).isDesigner = isDesigner
    const wrapper = mount(component as never, { global: { plugins: [pinia, router, Antd] } })
    await flushPromises()
    return wrapper
  }

  function findEntry(wrapper: ReturnType<typeof mount>) {
    // antd 会在两个中文字之间插空格，「追加字段」在 DOM 里是「追加字 段」
    return wrapper.findAll('button').find((b) => b.text().replace(/\s/g, '') === '追加字段')
  }

  it('设计者看得到入口，弹窗里有完整的追加表单', async () => {
    const { messages, restore } = watchUnresolved()
    try {
      const wrapper = await mountAs(InstanceDetailView, '/instance/1', true)

      const entry = findEntry(wrapper)
      expect(entry, '设计者应看到「追加字段」按钮').toBeTruthy()

      await entry!.trigger('click')
      await flushPromises()

      // 弹窗走 teleport 到 body，不在 wrapper.html() 里
      const modal = document.body.textContent?.replace(/\s+/g, '') ?? ''
      expect(modal).toContain('字段名称')
      expect(modal).toContain('可编辑节点')
      expect(modal).toContain('只能停用')   // 约束要写在界面上，不能只写在文档里
      expect(messages, `未注册的组件/指令：\n${messages.join('\n')}`).toEqual([])

      wrapper.unmount()
    } finally {
      restore()
    }
  })

  it('普通用户看不到入口', async () => {
    const wrapper = await mountAs(InstanceDetailView, '/instance/1', false)
    expect(findEntry(wrapper), '普通用户不该看到「追加字段」').toBeFalsy()
    wrapper.unmount()
  })
})


describe('驳回重提与快照对照', () => {
  /** 一张被驳回过的报销单：提交(轮1) → 驳回 → 重提(轮2) */
  function rejectedRender(): InstanceRender {
    const action = (
      id: number,
      kind: string,
      label: string,
      round: number,
      opinion: string | null,
      snapshotId: number | null,
    ): ActionEntry => ({
      action_id: id,
      action: kind,
      action_label: label,
      node_key: null,
      node_name: null,
      actor_id: id,
      actor_name: id === 2 ? '王经理' : '张三',
      opinion,
      round,
      from_status: null,
      to_status: null,
      changed_fields: [],
      attachments: [],
      snapshot_id: snapshotId,
      snapshot_seq: snapshotId,
      created_at: '2026-09-22T10:00:00',
    })

    return {
      instance: {
        id: 1,
        code: 'BX20260922-0001',
        title: '出差报销',
        status: 'REJECTED',
        round: 2,
        flow_template_id: 1,
        flow_template_name: '报销流程',
        flow_version_id: 1,
        form_version_id: 1,
        initiator_id: 1,
        initiator_name: '张三',
        initiator_dept_name: '技术部',
        current_node_keys: [],
        abnormal: false,
        pending_count: 0,
        done_count: 2,
        my_pending_count: 0,
        created_at: null,
        started_at: null,
        finished_at: null,
        last_action_at: null,
        terminated_reason: null,
      },
      my_role: 'INITIATOR',
      assignment: null,
      current_node: null,
      schema_data: {
        sections: [
          {
            key: 's',
            title: '申请信息',
            stage: 'apply',
            fields: [{ key: 'reason', label: '事由', type: 'text', required: true }],
          },
        ],
      },
      values: { reason: '初版事由' },
      permissions: { reason: { visible: true, editable: true, required: true } },
      progress: [],
      actions: [
        action(1, 'SUBMIT', '提交', 1, null, 1),
        action(2, 'REJECT', '驳回', 1, '发票不全，请补齐', null),
        action(1, 'RESUBMIT', '重新提交', 2, null, 2),
      ],
      allowed_actions: [],
      return_targets: [],
      attachments: [],
      snapshot: null,
      ext_fields: [],
    }
  }

  it('被驳回的单子把驳回意见顶到发起人眼前，并能打开重提表单', async () => {
    const { messages, restore } = watchUnresolved()
    try {
      const api = vi.mocked(instanceApi)
      api.render.mockResolvedValueOnce(rejectedRender())

      const wrapper = await mountView(InstanceDetailView, '/instance/1')
      await flushPromises()

      const text = wrapper.text().replace(/\s/g, '')
      expect(text, '驳回意见应直接显示出来').toContain('发票不全，请补齐')
      expect(text).toContain('第2轮')

      const resubmit = wrapper
        .findAll('button')
        .find((b) => b.text().replace(/\s/g, '') === '修改并重新提交')
      expect(resubmit, '发起人应能重新提交').toBeTruthy()

      await resubmit!.trigger('click')
      await flushPromises()

      const modal = document.body.textContent?.replace(/\s+/g, '') ?? ''
      expect(modal).toContain('确认重新提交')
      expect(modal).toContain('从第一个节点重新开始')
      expect(messages, `未注册的组件/指令：\n${messages.join('\n')}`).toEqual([])

      wrapper.unmount()
    } finally {
      restore()
    }
  })

  it('查看历史快照时给出变更对照', async () => {
    const api = vi.mocked(instanceApi)
    api.render.mockResolvedValue(rejectedRender())
    api.snapshotDiff.mockResolvedValueOnce([
      { key: 'reason', old: '初版事由', new: '补充发票后的事由' },
    ])

    const wrapper = await mountView(InstanceDetailView, '/instance/1')
    await flushPromises()

    // 时间线条目要展开才看得到快照入口
    const toggle = wrapper.findAll('a.toggle')[0]
    expect(toggle, '时间线应有「详情」展开入口').toBeTruthy()
    await toggle.trigger('click')
    await flushPromises()

    const link = wrapper
      .findAll('a')
      .find((a) => a.text().includes('查看当时的表单快照'))
    expect(link, '时间线应有快照入口').toBeTruthy()
    await link!.trigger('click')
    await flushPromises()

    const html = wrapper.text()
    expect(html).toContain('变更对照')
    // 字段引用要翻成中文标签，不能直接露出 reason
    expect(html).toContain('事由')

    wrapper.unmount()
  })
})

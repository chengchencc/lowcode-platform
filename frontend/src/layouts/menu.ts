/**
 * 侧边菜单的结构（PRD §5 的信息架构）。
 *
 * 单独成模块是为了**能被测试直接读到**：菜单项的 key 约定等于路由名，
 * 而「菜单项忘了接上路由」表现为「点了没反应」—— 是最难查的一类问题，
 * 已经出过两次：
 *   - 工作台：路由要求必填参数 `:type`，`push({name})` 不带参数会**静默中止导航**
 *   - 实例管理：菜单项加进来了，但没加进「可跳转白名单」
 * 现在白名单不再手维护（见 `navigableNames()`），并由测试遍历菜单项逐个断言跳得通。
 */
import type { MenuProps } from 'ant-design-vue'
import {
  ApartmentOutlined,
  AuditOutlined,
  DashboardOutlined,
  FolderOpenOutlined,
  FormOutlined,
  MessageOutlined,
  PartitionOutlined,
  RocketOutlined,
  ScheduleOutlined,
  SwapOutlined,
  TableOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { h } from 'vue'
import type { Router } from 'vue-router'

export interface MenuContext {
  isAdmin: boolean
  /** 设计者：可维护表单/流程模板。管理员天然拥有该能力（见后端 `policy.is_designer`）。 */
  isDesigner: boolean
  /** 待办数（角标） */
  todoCount: number
  /** 抄送未读数（角标） */
  ccUnread: number
}

export type MenuItem = NonNullable<MenuProps['items']>[number]

/**
 * 带**必填路径参数**的菜单项 → 默认参数。
 *
 * 少了它 `router.push({name})` 会因缺参而中止导航（Vue Router 不报错、
 * 页面也不跳，表现就是「点了没反应」）。工作台曾经就是这样打不开的。
 */
export const MENU_DEFAULT_PARAMS: Record<string, Record<string, string>> = {
  workbench: { type: 'todo' },
}

export function buildMenuItems(ctx: MenuContext): MenuItem[] {
  const badge = (count: number) =>
    count ? h('em', { class: 'menu-badge' }, String(count)) : null

  const items: MenuItem[] = [
    { key: 'dashboard', label: '首页', icon: () => h(DashboardOutlined) },
    { key: 'start-center', label: '发起中心', icon: () => h(RocketOutlined) },
    {
      key: 'workbench',
      label: h('span', { class: 'menu-label' }, ['工作台', badge(ctx.todoCount)]),
      icon: () => h(ScheduleOutlined),
    },
    { key: 'spreadsheets', label: '共享表格', icon: () => h(TableOutlined) },
    { key: 'delegations', label: '委托管理', icon: () => h(SwapOutlined) },
  ]

  // 审批管理（PRD §5：管理员/设计者）。普通用户看不到模板菜单 ——
  // 那两条路由要 designer 角色，露出来就是「点了被弹回首页」的死入口。
  if (ctx.isAdmin || ctx.isDesigner) {
    items.push({
      key: 'design',
      label: '审批管理',
      icon: () => h(PartitionOutlined),
      children: [
        { key: 'form-templates', label: '表单模板', icon: () => h(FormOutlined) },
        { key: 'flow-templates', label: '流程模板', icon: () => h(PartitionOutlined) },
        // 实例管理只给管理员：它是全组织单据的检索入口，不是「与我相关的」
        ...(ctx.isAdmin
          ? [{ key: 'instances', label: '实例管理', icon: () => h(FolderOpenOutlined) }]
          : []),
      ],
    })
  }

  if (ctx.isAdmin) {
    items.push({
      key: 'org',
      label: '组织管理',
      icon: () => h(ApartmentOutlined),
      children: [
        { key: 'org-users', label: '用户管理', icon: () => h(UserOutlined) },
        { key: 'org-depts', label: '部门管理', icon: () => h(ApartmentOutlined) },
        { key: 'org-roles', label: '角色管理', icon: () => h(TeamOutlined) },
      ],
    })
    items.push({ key: 'audit', label: '操作审计', icon: () => h(AuditOutlined) })
  }

  items.push({
    key: 'messages',
    label: h('span', { class: 'menu-label' }, ['消息中心', badge(ctx.ccUnread)]),
    icon: () => h(MessageOutlined),
  })

  return items
}

/** 递归取出所有**叶子**菜单项的 key（分组节点 'design'/'org' 自己不是路由）。 */
export function leafKeys(items: MenuItem[]): string[] {
  const out: string[] = []
  for (const item of items) {
    if (!item) continue
    const children = (item as { children?: MenuItem[] }).children
    if (children?.length) {
      out.push(...leafKeys(children))
      continue
    }
    const key = (item as { key?: string | number }).key
    if (key !== undefined) out.push(String(key))
  }
  return out
}

/**
 * 哪些菜单 key 可以直接跳转 —— **从路由表推导**，不再手维护白名单。
 *
 * 手维护的代价已经付过两次：新增页面时忘了加进去，点了没反应。
 * 规则：菜单 key 等于路由名，且该路由的路径参数都能由 `MENU_DEFAULT_PARAMS` 补齐
 * （workbench 的 `:type` 有默认值；设计器的 `:id` 没有 → 入口不在菜单里，也不算可跳转）。
 */
export function navigableNames(router: Router): Set<string> {
  const out = new Set<string>()
  for (const record of router.getRoutes()) {
    if (!record.name) continue
    const name = String(record.name)
    // 路径里的必填参数必须都能由 MENU_DEFAULT_PARAMS 补齐
    // （如 workbench 的 `:type` 有默认值 todo；设计器的 `:id` 没有 → 不算可跳转）
    const params = (record.path.match(/:[a-zA-Z_]+/g) ?? []).map((p) => p.slice(1))
    const defaults = MENU_DEFAULT_PARAMS[name] ?? {}
    if (params.every((param) => param in defaults)) out.add(name)
  }
  return out
}

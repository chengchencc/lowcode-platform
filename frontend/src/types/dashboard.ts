/** 首页聚合接口的 TS 类型，与 backend/app/schemas/dashboard.py 对齐。 */

import type { InstanceStatus } from '@/types/instance'

export interface DashboardStats {
  todo: number
  cc_unread: number
  mine_running: number
  mine_finished_this_month: number
}

export interface DashboardTodoItem {
  assignment_id: number
  instance_id: number
  title: string
  code: string | null
  node_name: string | null
  arrived_at: string | null
}

export interface DashboardInstanceItem {
  instance_id: number
  title: string
  status: InstanceStatus
  current_node_names: string[]
  updated_at: string | null
}

export interface DashboardFlowItem {
  flow_template_id: number
  name: string
  icon: string | null
}

export interface DashboardWorkStatItem {
  sheet_id: number
  name: string
  updated_at: string | null
}

export interface DashboardAdminByFlow {
  flow_template_id: number
  name: string
  count: number
}

export interface DashboardAdmin {
  running: number
  submitted_today: number
  finished_this_week: number
  pending_backlog: number
  by_flow: DashboardAdminByFlow[]
}

export interface DashboardOverview {
  personal: DashboardStats
  todos: DashboardTodoItem[]
  my_instances: DashboardInstanceItem[]
  quick_flows: DashboardFlowItem[]
  /** M12 工作量统计上线后填充；M11 恒为空数组 */
  work_stats: DashboardWorkStatItem[]
  admin: DashboardAdmin | null
}

/** 组织相关类型，对应后端 app/schemas/org.py 与 auth.py。 */

export type UserStatus = 'ACTIVE' | 'DISABLED'
export type DeptStatus = 'ACTIVE' | 'DISABLED'

export interface RoleBrief {
  id: number
  code: string
  name: string
}

export interface Role extends RoleBrief {
  description?: string | null
  is_builtin: boolean
  status: string
  member_count: number
  created_at?: string | null
}

export interface RoleInput {
  code: string
  name: string
  description?: string | null
  status?: string
}

export interface DeptNode {
  id: number
  name: string
  code: string
  parent_id: number | null
  path: string
  level: number
  manager_user_id: number | null
  manager_name: string | null
  sort_order: number
  status: string
  member_count: number
  children: DeptNode[]
}

export interface DeptBrief {
  id: number
  name: string
  code: string
}

export interface DeptInput {
  name: string
  code: string
  parent_id?: number | null
  manager_user_id?: number | null
  sort_order?: number
  status?: string
}

export interface DeptMember {
  id: number
  username: string
  real_name: string
  position?: string | null
  status: string
}

export interface UserItem {
  id: number
  username: string
  real_name: string
  email?: string | null
  phone?: string | null
  avatar?: string | null
  dept_id?: number | null
  dept_name?: string | null
  position?: string | null
  status: UserStatus
  is_superuser: boolean
  roles: RoleBrief[]
  last_login_at?: string | null
  created_at?: string | null
}

export interface UserInput {
  username?: string
  password?: string
  real_name?: string
  email?: string | null
  phone?: string | null
  dept_id?: number | null
  position?: string | null
  status?: UserStatus
  role_ids?: number[]
}

export interface UserOption {
  id: number
  username: string
  real_name: string
  dept_id?: number | null
  dept_name?: string | null
}

export interface UserListQuery {
  page?: number
  size?: number
  keyword?: string
  dept_id?: number | null
  include_sub_depts?: boolean
  status?: UserStatus | null
}

import type { RoleBrief } from './org'

export interface CurrentUser {
  id: number
  username: string
  real_name: string
  email?: string | null
  phone?: string | null
  avatar?: string | null
  position?: string | null
  dept_id?: number | null
  dept_name?: string | null
  is_superuser: boolean
  status: string
  roles: RoleBrief[]
  last_login_at?: string | null
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  expires_at: number
  user: CurrentUser
}

export interface RefreshResponse {
  access_token: string
  refresh_token: string
  expires_at: number
}

export interface MeResponse {
  user: CurrentUser
  is_admin: boolean
  is_designer: boolean
}

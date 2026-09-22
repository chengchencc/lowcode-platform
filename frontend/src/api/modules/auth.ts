import { request } from '@/api/http'
import type { LoginResponse, MeResponse, RefreshResponse } from '@/types/auth'
import type { OkResp } from '@/types/api'

export const authApi = {
  login(username: string, password: string) {
    // silent：登录失败要在表单里就地提示，不用全局 toast
    return request.post<LoginResponse>(
      '/auth/login',
      { username, password },
      { silent: true },
    )
  },

  refresh(refreshToken: string) {
    return request.post<RefreshResponse>('/auth/refresh', { refresh_token: refreshToken })
  },

  logout() {
    return request.post<OkResp>('/auth/logout')
  },

  me() {
    return request.get<MeResponse>('/auth/me')
  },

  changePassword(oldPassword: string, newPassword: string) {
    return request.post<OkResp>('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
}

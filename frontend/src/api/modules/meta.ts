import { request } from '@/api/http'

export interface AppMeta {
  name: string
  version: string
}

export const metaApi = {
  /** 公开接口；启动即取，失败不能弹提示打断登录页。 */
  get() {
    return request.get<AppMeta>('/meta', { silent: true, timeout: 5000 })
  },
}

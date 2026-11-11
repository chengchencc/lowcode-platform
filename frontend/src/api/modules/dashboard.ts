import { request } from '@/api/http'
import type { DashboardOverview } from '@/types/dashboard'

export const dashboardApi = {
  /** 首页一次取全：个人计数、待办预览、我发起的、常用流程、管理概览 */
  overview() {
    return request.get<DashboardOverview>('/dashboard/overview')
  },
}

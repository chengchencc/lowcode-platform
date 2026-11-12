import { request } from '@/api/http'
import type { OkResp } from '@/types/api'
import type { Delegation, DelegationPayload } from '@/types/delegation'

export const delegationApi = {
  list(allUsers = false) {
    return request.get<Delegation[]>('/delegations', { params: { all_users: allUsers } })
  },

  create(payload: DelegationPayload) {
    return request.post<Delegation>('/delegations', payload)
  },

  update(id: number, payload: Partial<DelegationPayload>) {
    return request.put<Delegation>(`/delegations/${id}`, payload)
  },

  cancel(id: number) {
    return request.post<Delegation>(`/delegations/${id}/cancel`)
  },
}

export const transferApi = {
  transfer(assignmentId: number, toUserId: number, reason: string) {
    return request.post<OkResp>(`/tasks/assignments/${assignmentId}/transfer`, {
      to_user_id: toUserId,
      reason,
    })
  },
}

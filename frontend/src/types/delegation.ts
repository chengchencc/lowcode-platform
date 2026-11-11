/** 转办与委托（M14）。 */

export interface Delegation {
  id: number
  delegator_id: number
  delegator_name: string | null
  delegatee_id: number
  delegatee_name: string | null
  start_at: string
  end_at: string
  flow_template_ids: number[] | null
  reason: string
  status: 'ACTIVE' | 'CANCELLED'
  created_at: string | null
}

export interface DelegationPayload {
  delegatee_id: number
  start_at: string
  end_at: string
  flow_template_ids?: number[] | null
  reason: string
}

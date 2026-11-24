import { request } from '@/api/http'
import type { OkResp } from '@/types/api'
import type {
  FlowDefinition,
  FlowTemplate,
  FlowValidateResult,
  FlowVersion,
  FlowVersionBrief,
  InitiatorScope,
  ReturnTarget,
} from '@/types/flow'

export const flowApi = {
  listTemplates(params?: {
    keyword?: string
    category?: string
    status?: string
    form_template_id?: number
  }) {
    return request.get<FlowTemplate[]>('/flow-templates', { params })
  },

  getTemplate(id: number) {
    return request.get<FlowTemplate>(`/flow-templates/${id}`)
  },

  createTemplate(payload: {
    name: string
    form_template_id: number
    code?: string | null
    category?: string | null
    description?: string | null
    initiator_scope?: InitiatorScope | null
  }) {
    return request.post<FlowTemplate>('/flow-templates', payload)
  },

  updateTemplate(
    id: number,
    payload: {
      name?: string
      category?: string | null
      description?: string | null
      initiator_scope?: InitiatorScope | null
    },
  ) {
    return request.put<FlowTemplate>(`/flow-templates/${id}`, payload)
  },

  setTemplateStatus(id: number, status: 'DRAFT' | 'DISABLED') {
    return request.post<FlowTemplate>(`/flow-templates/${id}/status`, { status })
  },

  deleteTemplate(id: number) {
    return request.delete<OkResp>(`/flow-templates/${id}`)
  },

  listVersions(templateId: number) {
    return request.get<FlowVersionBrief[]>(`/flow-templates/${templateId}/versions`)
  },

  /** 新建草稿版本；已存在草稿时后端直接复用并返回它（幂等） */
  createVersion(templateId: number) {
    return request.post<FlowVersion>(`/flow-templates/${templateId}/versions`)
  },

  getVersion(versionId: number) {
    return request.get<FlowVersion>(`/flow-versions/${versionId}`)
  },

  /**
   * 保存草稿。后端刻意不做语义校验（设计器要能存下没配完的流程），
   * 所以「审批人还没配」也能存；形状错误才会 422。
   */
  saveVersion(
    versionId: number,
    definition: FlowDefinition,
    options?: { locked_form_version_id?: number | null; remark?: string | null },
  ) {
    return request.put<FlowVersion>(`/flow-versions/${versionId}`, {
      definition,
      ...options,
    })
  },

  deleteVersion(versionId: number) {
    return request.delete<OkResp>(`/flow-versions/${versionId}`)
  },

  /** 权威校验（F2.7）：设计器的「发布前检查」用它 */
  validateVersion(versionId: number) {
    return request.post<FlowValidateResult>(`/flow-versions/${versionId}/validate`)
  },

  publishVersion(versionId: number, remark?: string | null) {
    return request.post<FlowVersion>(`/flow-versions/${versionId}/publish`, { remark })
  },

  /**
   * 某节点可退回的目标集合。
   *
   * 规则在服务端（`allowed_return_targets`），前端不重复实现 ——
   * 否则「哪些节点算前序」这种规则会在两边各写一遍并逐渐漂移。
   */
  returnTargets(versionId: number, nodeId: string) {
    return request.get<ReturnTarget[]>(`/flow-versions/${versionId}/return-targets`, {
      params: { node_id: nodeId },
      silent: true, // 编辑过程中 definition 还没保存，后端可能找不到新改的 node id —— 不该弹 toast
    })
  },
}

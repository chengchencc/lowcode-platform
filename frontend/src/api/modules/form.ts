import { request } from '@/api/http'
import type { OkResp } from '@/types/api'
import type {
  AttachmentInfo,
  FormPreview,
  FormSchema,
  FormTemplate,
  FormTemplateInput,
  FormValidateResult,
  FormVersion,
  FormVersionBrief,
} from '@/types/form'
import type { SearchFieldConfig } from '@/types/search'

export const formApi = {
  listTemplates(params?: { keyword?: string; group_name?: string; status?: string }) {
    return request.get<FormTemplate[]>('/form-templates', { params })
  },

  groups() {
    return request.get<string[]>('/form-templates/groups')
  },

  getTemplate(id: number) {
    return request.get<FormTemplate>(`/form-templates/${id}`)
  },

  createTemplate(payload: FormTemplateInput) {
    return request.post<FormTemplate>('/form-templates', payload)
  },

  updateTemplate(id: number, payload: Partial<FormTemplateInput>) {
    return request.put<FormTemplate>(`/form-templates/${id}`, payload)
  },

  setTemplateStatus(id: number, status: 'DRAFT' | 'DISABLED') {
    return request.post<FormTemplate>(`/form-templates/${id}/status`, { status })
  },

  copyTemplate(id: number, name: string, code?: string | null) {
    return request.post<FormTemplate>(`/form-templates/${id}/copy`, { name, code })
  },

  deleteTemplate(id: number) {
    return request.delete<OkResp>(`/form-templates/${id}`)
  },

  exportTemplate(id: number) {
    return request.get<Record<string, unknown>>(`/form-templates/${id}/export`)
  },

  importTemplate(payload: Record<string, unknown>) {
    return request.post<FormTemplate>('/form-templates/import', payload)
  },

  listVersions(templateId: number) {
    return request.get<FormVersionBrief[]>(`/form-templates/${templateId}/versions`)
  },

  /** 新建草稿版本；已存在草稿时后端直接复用并返回它（幂等） */
  createVersion(templateId: number, fromVersionId?: number | null) {
    return request.post<FormVersion>(`/form-templates/${templateId}/versions`, {
      from_version_id: fromVersionId ?? null,
    })
  },

  getVersion(versionId: number) {
    return request.get<FormVersion>(`/form-versions/${versionId}`)
  },

  /**
   * 保存草稿。后端刻意不做语义校验（设计器要能存下没配完的表单），
   * 所以这里不会因「单选还没配选项」而失败；形状错误才会 422。
   */
  saveVersion(versionId: number, schema_data: FormSchema, remark?: string | null) {
    return request.put<FormVersion>(`/form-versions/${versionId}`, { schema_data, remark })
  },

  deleteVersion(versionId: number) {
    return request.delete<OkResp>(`/form-versions/${versionId}`)
  },

  /** 权威校验：设计器的「发布前检查」用它 */
  validateVersion(versionId: number) {
    return request.post<FormValidateResult>(`/form-versions/${versionId}/validate`)
  },

  publishVersion(versionId: number, remark?: string | null) {
    return request.post<FormVersion>(`/form-versions/${versionId}/publish`, { remark })
  },

  /** 预览：服务端重算公式，返回与提交后一致的结果（决策 D4） */
  previewVersion(versionId: number, sampleData: Record<string, unknown> = {}) {
    return request.post<FormPreview>(`/form-versions/${versionId}/preview`, {
      sample_data: sampleData,
    })
  },

  /** 可检索字段配置（M13） */
  searchFields(id: number) {
    return request.get<SearchFieldConfig[]>(`/form-templates/${id}/search-fields`)
  },

  saveSearchFields(id: number, fieldKeys: string[]) {
    return request.put<{ added: number; removed: number; needs_backfill: boolean }>(
      `/form-templates/${id}/search-fields`,
      { field_keys: fieldKeys },
    )
  },

  /** 为存量实例重建检索索引（用当前已保存的字段配置） */
  rebuildSearchIndex(id: number) {
    return request.post<{ total: number; processed: number }>(
      `/form-templates/${id}/search-fields/rebuild`,
      undefined,
      { timeout: 120000 },
    )
  },
}

export const fileApi = {
  upload(file: File, imageOnly = false) {
    const form = new FormData()
    form.append('file', file)
    return request.post<AttachmentInfo>('/files/upload', form, {
      params: { image_only: imageOnly },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  remove(id: number) {
    return request.delete<OkResp>(`/files/${id}`)
  },

  /**
   * **浏览器直接访问**的下载地址，给 `<a href>` / `<img src>` 用。
   *
   * ⚠️ 不要把它传给 `request.get()` —— axios 的 baseURL 也是 `/api/v1`，
   * 会拼成 `/api/v1/api/v1/files/...` 而 404。
   * （httpx 在 Python 侧有同样的坑：base_url 遇到 `/` 开头的路径是追加而非替换。）
   */
  downloadUrl(id: number) {
    return `/api/v1/files/${id}/download`
  },

  /** 走 axios 时用的**相对路径**（实例的 baseURL 会补 /api/v1） */
  downloadPath(id: number) {
    return `/files/${id}/download`
  },

  /** 附件元数据（只读表单/打印里显示文件名） */
  info(id: number) {
    return request.get<AttachmentInfo>(`/files/${id}`)
  },
}

import { request } from '@/api/http'
import type { AiStatus } from '@/types/ai'
import type { FlowDefinition } from '@/types/flow'
import type { FormSchema } from '@/types/form'

export const aiApi = {
  status() {
    return request.get<AiStatus>('/ai/status', { silent: true })
  },

  generateForm(description: string, preferences?: string | null) {
    return request.post<{ schema_data: FormSchema }>('/ai/form-schema', {
      description,
      preferences: preferences || null,
    })
  },

  generateFlow(description: string, formSchema: FormSchema) {
    return request.post<{ definition: FlowDefinition }>('/ai/flow-definition', {
      description,
      form_schema: formSchema,
    })
  },
}

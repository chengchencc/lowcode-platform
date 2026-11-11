<script setup lang="ts">
import { Alert, Button, Input, Modal, Spin } from 'ant-design-vue'
import { ref, watch } from 'vue'

import { aiApi } from '@/api/modules/ai'
import type { FlowDefinition } from '@/types/flow'
import type { FormSchema } from '@/types/form'
import { feedback } from '@/utils/feedback'

const props = defineProps<{
  open: boolean
  kind: 'form' | 'flow'
  formSchema?: FormSchema | null
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  generated: [value: FormSchema | FlowDefinition]
}>()

const description = ref('')
const preferences = ref('')
const loading = ref(false)
const checking = ref(false)
const enabled = ref<boolean | null>(null)
const result = ref<FormSchema | FlowDefinition | null>(null)

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    description.value = ''
    preferences.value = ''
    result.value = null
    enabled.value = null
    checking.value = true
    try {
      enabled.value = (await aiApi.status()).enabled
    } catch {
      enabled.value = false
    } finally {
      checking.value = false
    }
  },
)

async function generate(): Promise<void> {
  if (!description.value.trim()) {
    feedback.error('请先描述业务')
    return
  }
  if (props.kind === 'flow' && !props.formSchema) {
    feedback.error('流程设计器还没有加载表单结构')
    return
  }
  loading.value = true
  try {
    if (props.kind === 'form') {
      const data = await aiApi.generateForm(description.value.trim(), preferences.value)
      result.value = data.schema_data
    } else {
      const data = await aiApi.generateFlow(description.value.trim(), props.formSchema!)
      result.value = data.definition
    }
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function apply(): void {
  if (!result.value) return
  emit('generated', result.value)
  emit('update:open', false)
}
</script>

<template>
  <Modal
    :open="open"
    :title="kind === 'form' ? 'AI 生成表单' : 'AI 生成流程'"
    width="820px"
    :footer="null"
    @update:open="emit('update:open', $event)"
  >
    <Spin :spinning="checking">
      <Alert
        v-if="enabled === false"
        type="warning"
        show-icon
        message="AI 功能未开启，请联系管理员配置模型与网络例外"
        class="mb"
      />

      <template v-else>
        <Alert
          type="info"
          show-icon
          class="mb"
          message="只发送业务描述和表单结构，不发送实例数据。生成结果是草稿，需要预览确认后才会写入设计器。"
        />

        <div class="form-row">
          <span class="label">业务描述</span>
          <Input.TextArea
            v-model:value="description"
            :rows="4"
            placeholder="例如：做一个出差申请，包含目的地、起止日期、交通方式、预计费用，部门经理和财务审批"
          />
        </div>
        <div v-if="kind === 'form'" class="form-row">
          <span class="label">配置偏好</span>
          <Input
            v-model:value="preferences"
            placeholder="选填，例如：不要子表；字段尽量少"
          />
        </div>

        <div class="actions">
          <Button type="primary" :loading="loading" :disabled="!enabled" @click="generate">
            {{ result ? '重新生成' : '生成' }}
          </Button>
        </div>

        <div v-if="result" class="result">
          <div class="result-title">生成预览</div>
          <pre class="preview">{{ JSON.stringify(result, null, 2) }}</pre>
          <Button type="primary" @click="apply">应用到设计器</Button>
        </div>
      </template>
    </Spin>
  </Modal>
</template>

<style scoped lang="scss">
.mb {
  margin-bottom: 12px;
}

.form-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.label {
  flex: 0 0 72px;
  padding-top: 4px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.result {
  margin-top: 16px;
}

.result-title {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}

.preview {
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  border-radius: 6px;
  background: #fafafa;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

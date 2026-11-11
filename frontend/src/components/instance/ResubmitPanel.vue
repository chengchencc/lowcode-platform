<script setup lang="ts">
/**
 * 驳回后的重提入口（PRD §3.5.1 / F3.6）。
 *
 * 驳回**不是终态**：发起人改完可以重新提交，轮次 +1，整条流程从头重走
 * （上一轮的处理记录与快照都留着，时间线上能对照）。
 *
 * 界面要做三件事：
 *   - 把驳回意见顶到眼前 —— 争议追溯靠的就是它，不该让人去时间线里翻
 *   - 让发起人只改该改的：按**发起节点**的权限渲染表单（服务端下发的同一份权限表）
 *   - 说明白重提的后果：从第一个节点重新走一遍
 *
 * 只提交改动过的字段；服务端还会按权限再过滤一次，非发起阶段可编辑的键会被忽略。
 */
import { Button, Modal } from 'ant-design-vue'
import { computed, ref } from 'vue'

import { instanceApi } from '@/api/modules/instance'
import { FormRenderer } from '@/components/form-renderer'
import type { FieldState } from '@/types/form'
import type { InstanceRender } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const props = defineProps<{ data: InstanceRender }>()
const emit = defineEmits<{ submitted: [] }>()

const AButton = Button

const open = ref(false)
const submitting = ref(false)
const note = ref('')
const values = ref<Record<string, unknown>>({})

/** 最近一次驳回：意见 + 谁驳的 + 什么时候 */
const rejection = computed(() => {
  const rows = props.data.actions.filter((a) => a.action === 'REJECT')
  return rows.length ? rows[rows.length - 1] : null
})

const permissions = computed<Record<string, FieldState>>(() => {
  const out: Record<string, FieldState> = {}
  const source = props.data.base_permissions ?? props.data.permissions ?? {}
  for (const [key, perm] of Object.entries(source)) {
    out[key] = { visible: perm.visible, editable: perm.editable, required: perm.required }
  }
  return out
})

const formRules = computed(
  () => props.data.form_rules ?? props.data.schema_data.rules ?? [],
)

const changedCount = computed(() => Object.keys(changedPatch.value).length)

/** 与「当前保存的值」的差异 —— 只提这些，别把整表单塞回去 */
const changedPatch = computed<Record<string, unknown>>(() => {
  const baseline = props.data.values ?? {}
  const patch: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(values.value)) {
    if (JSON.stringify(baseline[key]) !== JSON.stringify(value)) patch[key] = value
  }
  return patch
})

function openModal(): void {
  values.value = { ...(props.data.values ?? {}) }
  note.value = ''
  open.value = true
}

async function submit(): Promise<void> {
  submitting.value = true
  try {
    await instanceApi.resubmit(props.data.instance.id, {
      data: changedPatch.value,
      note: note.value.trim() || null,
    })
    feedback.success('已重新提交，流程从头开始走')
    open.value = false
    emit('submitted')
  } catch {
    // 拦截器已提示（必填缺失 / 校验不通过 / 状态已变…）
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <a-alert
    type="warning"
    show-icon
    class="reject-alert"
    :message="`被驳回：${rejection?.opinion || '（无意见）'}`"
    :description="rejection
      ? `${rejection.actor_name} 于 ${formatDateTime(rejection.created_at)} 驳回；修改后重新提交将从头重走整条流程（轮次 +1）`
      : undefined"
  >
    <template #action>
      <AButton type="primary" @click="openModal">修改并重新提交</AButton>
    </template>
  </a-alert>

  <Modal
    v-model:open="open"
    title="重新提交"
    :width="880"
    :confirm-loading="submitting"
    ok-text="确认重新提交"
    cancel-text="取消"
    @ok="submit"
  >
    <a-alert
      type="info"
      show-icon
      class="mb"
      message="提交后流程从第一个节点重新开始"
      description="上一轮的处理记录与快照都会保留，可在「处理历史」里对照。"
    />

    <FormRenderer
      :schema="data.schema_data"
      :model-value="values"
      :permissions="permissions"
      :rules="formRules"
      mode="edit"
      @update:model-value="values = $event"
    />

    <a-form-item label="补充说明" class="note">
      <a-textarea
        v-model:value="note"
        :rows="2"
        :maxlength="2000"
        placeholder="选填，会记入处理历史"
      />
    </a-form-item>

    <div class="text-muted changed">
      {{ changedCount ? `已改动 ${changedCount} 个字段` : '还没有改动任何字段' }}
    </div>
  </Modal>
</template>

<style scoped lang="scss">
.reject-alert {
  margin-bottom: 12px;
}

.mb {
  margin-bottom: 12px;
}

.note {
  margin-top: 12px;
}

.changed {
  font-size: 12px;
}
</style>

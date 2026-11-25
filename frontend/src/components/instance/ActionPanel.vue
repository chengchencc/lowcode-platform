<script setup lang="ts">
/**
 * 处理操作区（PRD F4.3）。
 *
 * 三种动作的语义差别很大，界面上要能看出来：
 * - **同意**：继续往下走
 * - **驳回**：打回发起人，实例变「已驳回」，重提要**从头重走**；必须写意见
 * - **退回**：退给某个前序节点，实例**仍在审批中**，只重派那一段
 *
 * 「可退回给谁」由服务端算（`/return-targets`），前端只负责展示。
 * 处理时改动的字段会**只提交可编辑的那些**，服务端还会再按权限过滤一次。
 */
import { UploadOutlined } from '@ant-design/icons-vue'
import { Button, Upload } from 'ant-design-vue'
import { computed, ref } from 'vue'

import { fileApi } from '@/api/modules/form'
import type { AttachmentInfo } from '@/types/form'
import type { ActPayload, InstanceRender, TaskAction } from '@/types/instance'
import { ACTION_LABELS } from '@/types/instance'
import { feedback } from '@/utils/feedback'
import { fieldLabelIndex } from '@/utils/fieldValueDisplay'

const props = defineProps<{
  data: InstanceRender
  /** 处理时被改动过的字段值（由详情页维护），只提交这些 */
  fieldPatch: Record<string, unknown>
}>()

const emit = defineEmits<{
  acted: []
  'clear-patch': []
}>()

const AButton = Button
const AUpload = Upload

const modalOpen = ref(false)
const action = ref<TaskAction>('AGREE')
const opinion = ref('')
const returnTarget = ref<string | null>(null)
const attachments = ref<AttachmentInfo[]>([])
const submitting = ref(false)
const uploading = ref(false)

const node = computed(() => props.data.current_node)
const targets = computed(() => props.data.return_targets)
const changedKeys = computed(() => Object.keys(props.fieldPatch))
/** 预览给人看的字段名；schema 里找不到时才退回 key */
const changedLabels = computed(() => {
  const labels = fieldLabelIndex(props.data.schema_data)
  return changedKeys.value.map((key) => labels[key] ?? key)
})

/** 该动作是否需要意见（驳回必填；节点可配「意见必填」） */
const opinionRequired = computed(() => {
  if (action.value === 'REJECT') return true
  return Boolean(node.value?.opinion_required)
})

const attachmentRequired = computed(() => Boolean(node.value?.attachment_required))

const canSubmit = computed(() => {
  if (opinionRequired.value && !opinion.value.trim()) return false
  if (attachmentRequired.value && !attachments.value.length) return false
  if (action.value === 'RETURN' && !returnTarget.value) return false
  return true
})

function open(next: TaskAction): void {
  action.value = next
  opinion.value = ''
  returnTarget.value = null
  attachments.value = []
  modalOpen.value = true
}

async function upload(file: File): Promise<boolean> {
  uploading.value = true
  try {
    const info = await fileApi.upload(file)
    attachments.value = [...attachments.value, info]
  } catch {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
  return false
}

function removeAttachment(id: number): void {
  attachments.value = attachments.value.filter((a) => a.id !== id)
}

async function submit(): Promise<void> {
  if (!props.data.assignment) return
  submitting.value = true

  const payload: ActPayload = {
    action: action.value,
    opinion: opinion.value.trim() || null,
    attachment_ids: attachments.value.map((a) => a.id),
    field_patch: props.fieldPatch,
    return_target: action.value === 'RETURN' ? returnTarget.value : null,
  }

  try {
    const { taskApi } = await import('@/api/modules/instance')
    await taskApi.act(props.data.assignment.assignment_id, payload)
    feedback.success(`已${ACTION_LABELS[action.value]}`)
    modalOpen.value = false
    emit('clear-patch')
    emit('acted')
  } catch {
    // 拦截器已提示（幂等冲突 / 版本过期 / 权限…）
  } finally {
    submitting.value = false
  }
}

const ACTION_HINTS: Record<TaskAction, string> = {
  AGREE: '同意后流程继续往下走',
  REJECT: '打回发起人；发起人修改后需**从头重走**整条流程',
  RETURN: '退给某个前序节点；实例仍在审批中，只重派退回之后的部分',
  SUBMIT: '提交本节点的补充内容，流程继续往下走',
}
</script>

<template>
  <!-- 内联工具条，嵌在详情页标题栏右侧（不再独占一个面板） -->
  <span v-if="data.allowed_actions.length" class="action-toolbar">
    <template v-if="changedKeys.length">
      <a-tag color="orange" class="changed-tag">
        {{ changedKeys.length }} 个字段已修改
      </a-tag>
      <a class="discard" @click="emit('clear-patch')">放弃</a>
    </template>

    <AButton
      v-for="act in data.allowed_actions"
      :key="act"
      :type="act === 'AGREE' || act === 'SUBMIT' ? 'primary' : 'default'"
      :danger="act === 'REJECT'"
      @click="open(act)"
    >
      {{ ACTION_LABELS[act] }}
    </AButton>

    <a-modal
      v-model:open="modalOpen"
      :title="ACTION_LABELS[action]"
      :width="560"
      :confirm-loading="submitting"
      :ok-button-props="{ disabled: !canSubmit }"
      :ok-text="`确认${ACTION_LABELS[action]}`"
      cancel-text="取消"
      @ok="submit"
    >
      <a-alert
        :type="action === 'REJECT' ? 'warning' : 'info'"
        show-icon
        class="hint"
        :message="ACTION_HINTS[action].replace(/\*\*/g, '')"
      />

      <!-- 退回目标 -->
      <a-form-item v-if="action === 'RETURN'" label="退回到" required>
        <a-select
          v-model:value="returnTarget"
          :options="targets.map((t) => ({ value: t.node_id, label: t.name }))"
          placeholder="选择要退回的节点"
        />
        <template #extra>
          <span class="text-muted">
            候选由流程结构算出；退回后该节点会重新收到待办，之前已通过的节点不重走
          </span>
        </template>
      </a-form-item>

      <!-- 意见 -->
      <a-form-item
        label="审批意见"
        :required="opinionRequired"
        :help="action === 'REJECT' ? '驳回必须说明理由，否则发起人不知道要改什么' : undefined"
      >
        <a-textarea
          v-model:value="opinion"
          :rows="3"
          :placeholder="opinionRequired ? '必填' : '选填'"
          show-count
          :maxlength="2000"
        />
      </a-form-item>

      <!-- 附件 -->
      <a-form-item label="附件" :required="attachmentRequired">
        <div class="attachment-list">
          <a-tag v-for="att in attachments" :key="att.id" closable @close="removeAttachment(att.id)">
            {{ att.file_name }}
          </a-tag>
        </div>
        <AUpload :before-upload="upload" :show-upload-list="false" :disabled="uploading">
          <AButton size="small" :loading="uploading">
            <template #icon><UploadOutlined /></template>
            上传附件
          </AButton>
        </AUpload>
      </a-form-item>

      <!-- 改动预览 -->
      <a-alert
        v-if="changedKeys.length"
        type="warning"
        show-icon
        class="hint"
        :message="`本次将提交 ${changedKeys.length} 个字段的修改：${changedLabels.join('、')}`"
      />
    </a-modal>
  </span>
</template>

<style scoped lang="scss">
.action-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.changed-tag {
  margin: 0;
}

.discard {
  font-size: 12px;
}

.hint {
  margin-bottom: 12px;

  :deep(.ant-alert-message) {
    font-size: 12px;
  }
}

.attachment-list {
  margin-bottom: 6px;
}
</style>

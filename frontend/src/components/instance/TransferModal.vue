<script setup lang="ts">
import { Input, Modal, Select } from 'ant-design-vue'
import { ref, watch } from 'vue'

import { transferApi } from '@/api/modules/delegation'
import { userApi } from '@/api/modules/user'
import { feedback } from '@/utils/feedback'

const props = defineProps<{
  open: boolean
  assignmentId: number | null
  instanceTitle?: string
}>()
const emit = defineEmits<{ 'update:open': [value: boolean]; transferred: [] }>()

const users = ref<Array<{ value: number; label: string }>>([])
const toUserId = ref<number | undefined>()
const reason = ref('')
const saving = ref(false)

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    toUserId.value = undefined
    reason.value = ''
    try {
      const options = await userApi.options({ limit: 200 })
      users.value = options.map((user) => ({
        value: user.id,
        label: `${user.real_name}${user.dept_name ? `（${user.dept_name}）` : ''}`,
      }))
    } catch {
      users.value = []
    }
  },
)

async function submit(): Promise<void> {
  if (!props.assignmentId) return
  if (!toUserId.value) {
    feedback.error('请选择转办给谁')
    return
  }
  if (!reason.value.trim()) {
    feedback.error('请填写转办原因')
    return
  }
  saving.value = true
  try {
    await transferApi.transfer(props.assignmentId, toUserId.value, reason.value.trim())
    feedback.success('已转办')
    emit('transferred')
    emit('update:open', false)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="`转办${instanceTitle ? ` · ${instanceTitle}` : ''}`"
    :confirm-loading="saving"
    ok-text="确认转办"
    cancel-text="取消"
    @ok="submit"
    @update:open="emit('update:open', $event)"
  >
    <div class="form-row">
      <span class="label">转办给</span>
      <Select
        v-model:value="toUserId"
        :options="users"
        show-search
        option-filter-prop="label"
        placeholder="选择人员"
        class="control"
      />
    </div>
    <div class="form-row">
      <span class="label">原因</span>
      <Input v-model:value="reason" placeholder="必填，会写入处理历史" class="control" />
    </div>
  </Modal>
</template>

<style scoped lang="scss">
.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.label {
  flex: 0 0 56px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.control {
  flex: 1;
}
</style>

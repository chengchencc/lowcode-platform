<script setup lang="ts">
import { Alert, Checkbox, Empty, Modal, Spin, Tag } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import { formApi } from '@/api/modules/form'
import type { SearchFieldConfig } from '@/types/search'
import { feedback } from '@/utils/feedback'

const props = defineProps<{ open: boolean; templateId: number; templateName?: string }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [] }>()

const loading = ref(false)
const saving = ref(false)
const fields = ref<SearchFieldConfig[]>([])
const selected = ref<string[]>([])

const selectedCount = computed(() => selected.value.length)

async function load(): Promise<void> {
  if (!props.templateId) return
  loading.value = true
  try {
    fields.value = await formApi.searchFields(props.templateId)
    selected.value = fields.value.filter((item) => item.selected).map((item) => item.field_key)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void load()
  },
)

function toggle(key: string, event: { target?: { checked?: boolean } }): void {
  const checked = !!event.target?.checked
  selected.value = checked
    ? [...selected.value, key]
    : selected.value.filter((item) => item !== key)
}

async function save(): Promise<void> {
  saving.value = true
  try {
    const result = await formApi.saveSearchFields(props.templateId, selected.value)
    feedback.success(
      result.needs_backfill
        ? '已保存；新字段需要对存量实例执行索引重建'
        : '已保存',
    )
    emit('saved')
    emit('update:open', false)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="`可检索字段${templateName ? ` · ${templateName}` : ''}`"
    :confirm-loading="saving"
    ok-text="保存"
    cancel-text="取消"
    width="720px"
    @ok="save"
    @update:open="emit('update:open', $event)"
  >
    <Alert
      type="info"
      show-icon
      class="panel-hint"
      message="勾选的字段会写入实例索引，用于归档/我发起的列表筛选。作用于该表单模板的所有版本。"
    />

    <Spin :spinning="loading">
      <div v-if="fields.length" class="field-list">
        <label v-for="field in fields" :key="field.field_key" class="field-row">
          <Checkbox
            :checked="selected.includes(field.field_key)"
            @change="toggle(field.field_key, $event)"
          />
          <span class="field-label">{{ field.label }}</span>
          <Tag class="field-kind">{{ field.filter_kind }}</Tag>
          <Tag v-if="!field.start_visible" color="orange" class="field-kind">
            发起阶段不可见
          </Tag>
          <span class="field-key text-mono text-muted">{{ field.field_key }}</span>
        </label>
      </div>
      <Empty v-else description="该表单还没有可检索字段" />
    </Spin>

    <div class="panel-footer text-muted">已选 {{ selectedCount }} / 20</div>
  </Modal>
</template>

<style scoped lang="scss">
.panel-hint {
  margin-bottom: 12px;
}

.field-list {
  max-height: 420px;
  overflow: auto;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;

  &:last-child {
    border-bottom: none;
  }
}

.field-label {
  font-size: 13px;
}

.field-kind {
  margin: 0;
  font-size: 11px;
}

.field-key {
  margin-left: auto;
  font-size: 11px;
}

.panel-footer {
  margin-top: 8px;
  font-size: 12px;
}
</style>

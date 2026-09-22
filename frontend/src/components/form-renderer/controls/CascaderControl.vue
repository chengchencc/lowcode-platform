<script setup lang="ts">
/**
 * 级联下拉（PRD §3.2.2 增强项）。
 *
 * 简化语义：本字段的候选项由某个「父字段」的当前值决定。
 * 父字段还没选时给出提示而不是空下拉 —— 否则用户不知道要先去填别的地方。
 */
import { computed } from 'vue'

import type { FieldDef } from '@/types/form'
import { cascaderOptions, formatValue } from '@/utils/formValue'

const props = defineProps<{
  field: FieldDef
  modelValue: unknown
  editable: boolean
  /** 当前表单的全部值，用于读父字段 */
  values?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [unknown] }>()

const parentKey = computed(() => props.field.cascader?.parent_field ?? '')
const parentValue = computed(() => (props.values ?? {})[parentKey.value])

const parentSelected = computed(
  () => parentValue.value !== null && parentValue.value !== undefined && parentValue.value !== '',
)

const options = computed(() =>
  cascaderOptions(props.field, props.values ?? {}).map((o) => ({
    label: o.label,
    value: o.value,
  })),
)

const readonlyText = computed(() => formatValue(props.field, props.modelValue))
</script>

<template>
  <span v-if="!editable" class="readonly-value">{{ readonlyText }}</span>

  <template v-else>
    <a-select
      :value="(modelValue as string | number | undefined)"
      :options="options"
      :placeholder="
        parentSelected ? field.placeholder || `请选择${field.label}` : '请先填写上级选项'
      "
      :disabled="!parentSelected"
      allow-clear
      show-search
      option-filter-prop="label"
      style="width: 100%"
      @update:value="emit('update:modelValue', $event ?? null)"
    />
    <div v-if="!parentSelected" class="text-muted hint">
      该选项列表由「{{ parentKey }}」的值决定
    </div>
  </template>
</template>

<style scoped>
.readonly-value {
  white-space: pre-wrap;
  word-break: break-word;
}

.hint {
  margin-top: 4px;
  font-size: 12px;
}
</style>

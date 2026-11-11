<script setup lang="ts">
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { Button, Input, Select } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import { instanceApi } from '@/api/modules/instance'
import type { FilterKind, SearchFieldMeta } from '@/types/search'

interface Condition {
  field: string
  op: string
  value: any
  valueTo?: any
}

const props = defineProps<{
  flowTemplateId: number | null | undefined
  scope: 'mine' | 'archive'
  modelValue: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const fields = ref<SearchFieldMeta[]>([])
const conditions = ref<Condition[]>([])
const loading = ref(false)

const TEXT_OPS = [
  { value: 'contains', label: '包含' },
  { value: 'eq', label: '等于' },
  { value: 'is_empty', label: '为空' },
  { value: 'is_not_empty', label: '不为空' },
]
const NUMBER_OPS = [
  { value: 'eq', label: '等于' },
  { value: 'gt', label: '大于' },
  { value: 'gte', label: '大于等于' },
  { value: 'lt', label: '小于' },
  { value: 'lte', label: '小于等于' },
  { value: 'between', label: '区间' },
  { value: 'is_empty', label: '为空' },
  { value: 'is_not_empty', label: '不为空' },
]
const DATE_OPS = [
  { value: 'eq', label: '等于' },
  { value: 'gte', label: '不早于' },
  { value: 'lte', label: '不晚于' },
  { value: 'between', label: '区间' },
  { value: 'is_empty', label: '为空' },
  { value: 'is_not_empty', label: '不为空' },
]
const OPTION_OPS = [
  { value: 'eq', label: '等于' },
  { value: 'in', label: '属于' },
  { value: 'is_empty', label: '为空' },
  { value: 'is_not_empty', label: '不为空' },
]
const MULTI_OPS = [
  { value: 'has_any', label: '包含任一' },
  { value: 'has_all', label: '包含全部' },
  { value: 'is_empty', label: '为空' },
  { value: 'is_not_empty', label: '不为空' },
]
const USER_OPS = [
  { value: 'eq', label: '等于' },
  { value: 'in', label: '属于' },
  { value: 'is_empty', label: '为空' },
  { value: 'is_not_empty', label: '不为空' },
]
const BOOL_OPS = [
  { value: 'eq', label: '等于' },
  { value: 'is_empty', label: '为空' },
  { value: 'is_not_empty', label: '不为空' },
]

function opsFor(kind: FilterKind | undefined) {
  if (!kind) return TEXT_OPS
  if (kind === 'number') return NUMBER_OPS
  if (['date', 'time', 'datetime'].includes(kind)) return DATE_OPS
  if (kind === 'bool') return BOOL_OPS
  if (['multi_option', 'user_multi', 'dept_multi'].includes(kind)) return MULTI_OPS
  if (['user', 'dept'].includes(kind)) return USER_OPS
  return OPTION_OPS
}

function fieldOf(key: string): SearchFieldMeta | undefined {
  return fields.value.find((field) => field.field_key === key)
}

function isNoValue(op: string): boolean {
  return op === 'is_empty' || op === 'is_not_empty'
}

function isRange(op: string): boolean {
  return op === 'between'
}

function isMultiValue(op: string): boolean {
  return op === 'in' || op === 'has_any' || op === 'has_all'
}

function isDateKind(kind: FilterKind | undefined): boolean {
  return kind === 'date' || kind === 'datetime'
}

function isNumberKind(kind: FilterKind | undefined): boolean {
  return kind === 'number' || kind === 'user' || kind === 'dept'
}

const fieldOptions = computed(() =>
  fields.value.map((field) => ({ value: field.field_key, label: field.label })),
)

async function load(): Promise<void> {
  conditions.value = []
  emit('update:modelValue', '')
  if (!props.flowTemplateId) {
    fields.value = []
    return
  }
  loading.value = true
  try {
    fields.value = await instanceApi.searchFields(props.flowTemplateId, props.scope)
  } catch {
    fields.value = []
  } finally {
    loading.value = false
  }
}

watch(() => [props.flowTemplateId, props.scope], load, { immediate: true })

function addCondition(): void {
  conditions.value.push({ field: '', op: 'contains', value: '' })
}

function removeCondition(index: number): void {
  conditions.value.splice(index, 1)
  emitFilters()
}

function onFieldChange(condition: Condition): void {
  const kind = fieldOf(condition.field)?.filter_kind
  condition.op = opsFor(kind)[0]?.value ?? 'eq'
  condition.value = ''
  condition.valueTo = ''
  emitFilters()
}

function optionList(condition: Condition) {
  const field = fieldOf(condition.field)
  return (field?.options ?? []).map((option) => ({
    value: String(option),
    label: String(option),
  }))
}

function hasUsableValue(condition: Condition): boolean {
  if (isNoValue(condition.op)) return true
  if (isRange(condition.op)) {
    return (
      condition.value !== '' && condition.value != null
      && condition.valueTo !== '' && condition.valueTo != null
    )
  }
  if (isMultiValue(condition.op)) {
    return String(condition.value ?? '').trim() !== ''
  }
  return condition.value !== '' && condition.value != null
}

function emitFilters(): void {
  const items = conditions.value
    .filter((condition) => condition.field && condition.op && hasUsableValue(condition))
    .map((condition) => {
      const field = fieldOf(condition.field)
      const kind = field?.filter_kind
      if (isNoValue(condition.op)) {
        return { field: condition.field, op: condition.op }
      }
      if (isRange(condition.op)) {
        const low = isNumberKind(kind) ? Number(condition.value) : condition.value
        const high = isNumberKind(kind) ? Number(condition.valueTo) : condition.valueTo
        return { field: condition.field, op: condition.op, value: [low, high] }
      }
      if (isMultiValue(condition.op)) {
        const raw = String(condition.value ?? '').trim()
        const parts = raw.split(',').map((part) => part.trim()).filter(Boolean)
        const value = isNumberKind(kind) ? parts.map(Number) : parts
        return { field: condition.field, op: condition.op, value }
      }
      let value: unknown = condition.value
      if (isNumberKind(kind)) value = Number(value)
      else if (kind === 'bool') value = value === true || value === 'true'
      return { field: condition.field, op: condition.op, value }
    })
    .filter((item) => {
      if (!('value' in item)) return true
      if (Array.isArray(item.value)) {
        return item.value.length > 0 && item.value.every((value) => value !== null && value !== '')
      }
      return item.value !== '' && item.value != null
    })

  emit('update:modelValue', items.length ? JSON.stringify(items) : '')
}

function onValueChange(): void {
  emitFilters()
}
</script>

<template>
  <div class="filter-builder">
    <div class="builder-head">
      <span class="text-muted builder-title">业务字段筛选</span>
      <Button size="small" :disabled="!fields.length" @click="addCondition">
        <template #icon><PlusOutlined /></template>
        添加条件
      </Button>
    </div>

    <div v-if="!flowTemplateId" class="text-muted builder-hint">
      选择一个流程后可按业务字段筛选
    </div>
    <div v-else-if="!loading && !fields.length" class="text-muted builder-hint">
      该流程的表单还没有配置可检索字段
    </div>

    <div v-for="(condition, index) in conditions" :key="index" class="condition-row">
      <Select
        v-model:value="condition.field"
        :options="fieldOptions"
        placeholder="字段"
        class="field-select"
        show-search
        option-filter-prop="label"
        @change="onFieldChange(condition)"
      />
      <Select
        v-model:value="condition.op"
        :options="opsFor(fieldOf(condition.field)?.filter_kind)"
        class="op-select"
        @change="onValueChange"
      />

      <template v-if="!isNoValue(condition.op)">
        <Select
          v-if="fieldOf(condition.field)?.filter_kind === 'bool'"
          v-model:value="condition.value"
          :options="[{ value: 'true', label: '是' }, { value: 'false', label: '否' }]"
          class="value-input"
          @change="onValueChange"
        />
        <Select
          v-else-if="fieldOf(condition.field)?.filter_kind === 'option' && condition.op === 'eq'"
          v-model:value="condition.value"
          :options="optionList(condition)"
          class="value-input"
          show-search
          option-filter-prop="label"
          @change="onValueChange"
        />
        <template v-else-if="isRange(condition.op)">
          <input
            v-model="condition.value"
            :type="isDateKind(fieldOf(condition.field)?.filter_kind) ? 'date' : isNumberKind(fieldOf(condition.field)?.filter_kind) ? 'number' : 'text'"
            class="native-input"
            @change="onValueChange"
          />
          <span class="text-muted">至</span>
          <input
            v-model="condition.valueTo"
            :type="isDateKind(fieldOf(condition.field)?.filter_kind) ? 'date' : isNumberKind(fieldOf(condition.field)?.filter_kind) ? 'number' : 'text'"
            class="native-input"
            @change="onValueChange"
          />
        </template>
        <Input
          v-else
          v-model:value="condition.value"
          :placeholder="isMultiValue(condition.op) ? '多个值用逗号分隔' : '值'"
          class="value-input"
          @change="onValueChange"
        />
      </template>

      <Button type="text" danger size="small" @click="removeCondition(index)">
        <template #icon><DeleteOutlined /></template>
      </Button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.filter-builder {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.builder-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.builder-title {
  font-size: 12px;
}

.builder-hint {
  margin-top: 6px;
  font-size: 12px;
}

.condition-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.field-select {
  width: 190px;
}

.op-select {
  width: 130px;
}

.value-input {
  width: 180px;
}

.native-input {
  width: 150px;
  height: 30px;
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 13px;
}
</style>

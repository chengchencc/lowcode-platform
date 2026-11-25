<script setup lang="ts">
/**
 * 人员 / 部门控件（PRD §3.2.2 组织分组）。
 *
 * 只读态下要把 id 换成人名/部门名 —— 值本身不自解释。
 * 名字来自 org store 的缓存（部门树常驻；人员是曾经出现在候选项里的）。
 */
import { TreeSelect } from 'ant-design-vue'
import { computed, onMounted } from 'vue'

import UserSelect from '@/components/common/UserSelect.vue'
import { useOrgStore } from '@/stores/org'
import type { FieldDef } from '@/types/form'
import { formatValue } from '@/utils/formValue'

const props = defineProps<{
  field: FieldDef
  modelValue: unknown
  editable: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [unknown] }>()

const org = useOrgStore()

const isUser = computed(() => props.field.type === 'user' || props.field.type === 'user_multi')
const isMulti = computed(() => props.field.type.endsWith('_multi'))

const deptValue = computed(() => {
  const v = props.modelValue
  if (v === null || v === undefined || v === '') return undefined
  if (isMulti.value) return Array.isArray(v) ? v.map(Number) : [Number(v)]
  return Number(v)
})

/** 只读展示：把 id 换成名字 */
const display = computed(() =>
  formatValue(props.field, props.modelValue, (kind, id) => {
    if (kind === 'dept') return org.deptName(Number(id))
    return org.userName(Number(id))
  }),
)

onMounted(() => {
  if (isUser.value || props.field.type.startsWith('dept')) void org.loadDeptTree()
})

function onUserChange(value: unknown): void {
  emit('update:modelValue', value ?? null)
}

function onDeptChange(value: unknown): void {
  emit('update:modelValue', value ?? null)
}
</script>

<template>
  <span v-if="!editable" class="readonly-value">{{ display }}</span>

  <UserSelect
    v-else-if="isUser"
    :model-value="(modelValue as number | number[] | null)"
    :multiple="isMulti"
    :placeholder="field.placeholder || '请选择人员'"
    @update:model-value="onUserChange"
  />

  <TreeSelect
    v-else
    :value="deptValue"
    :tree-data="org.deptTree"
    :field-names="{ children: 'children', label: 'name', value: 'id' }"
    :multiple="isMulti"
    :placeholder="field.placeholder || '请选择部门'"
    :tree-default-expand-all="true"
    allow-clear
    tree-checkable
    style="width: 100%"
    @change="onDeptChange"
  />
</template>

<style scoped>
.readonly-value {
  display: block;
  min-height: 22px;
  line-height: 1.5715;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

<script setup lang="ts">
/**
 * 表单联动规则的条件编辑器（M9）。
 *
 * 顶层的 and/or 与叶子条件可编辑；嵌套组保留原样并提示去 JSON 编辑 ——
 * 与流程条件编辑器当前的能力保持一致，不在这里悄悄丢掉已有配置。
 */
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'

import type { Comparison, Condition, ConditionGroup } from '@/types/conditions'
import { isConditionGroup } from '@/types/conditions'
import { COMPARISON_LABELS } from '@/types/flow'

const props = defineProps<{
  group: ConditionGroup
  fieldOptions: Array<{ value: string; label: string }>
}>()

const emit = defineEmits<{ change: [] }>()

const comparisonOptions = (Object.keys(COMPARISON_LABELS) as Comparison[]).map((cmp) => ({
  value: cmp,
  label: COMPARISON_LABELS[cmp],
}))

const opOptions = [
  { value: 'and', label: '同时满足（且）' },
  { value: 'or', label: '满足任一（或）' },
]

function notify(): void {
  emit('change')
}

function leafConditions(): Array<{ condition: Condition; index: number }> {
  const out: Array<{ condition: Condition; index: number }> = []
  props.group.conditions.forEach((item, index) => {
    if (!isConditionGroup(item)) out.push({ condition: item, index })
  })
  return out
}

const hasNested = computed(() => props.group.conditions.some((item) => isConditionGroup(item)))

function addCondition(): void {
  props.group.conditions.push({
    field: props.fieldOptions[0]?.value ?? '',
    cmp: '==',
    value: '',
  })
  notify()
}

function removeAt(index: number): void {
  props.group.conditions.splice(index, 1)
  notify()
}

function needsValue(cmp: Comparison): boolean {
  return cmp !== 'is_empty' && cmp !== 'is_not_empty'
}

function onValueInput(condition: Condition, event: Event): void {
  condition.value = (event.target as HTMLInputElement).value
  notify()
}
</script>

<template>
  <div class="condition-editor">
    <div class="op-row">
      <span class="text-muted">条件关系</span>
      <a-select v-model:value="group.op" :options="opOptions" size="small" @change="notify" />
    </div>

    <div
      v-for="entry in leafConditions()"
      :key="entry.index"
      class="condition-row"
    >
      <a-select
        v-model:value="entry.condition.field"
        :options="fieldOptions"
        size="small"
        placeholder="字段"
        show-search
        option-filter-prop="label"
        class="field-select"
        @change="notify"
      />
      <a-select
        v-model:value="entry.condition.cmp"
        :options="comparisonOptions"
        size="small"
        class="cmp-select"
        @change="notify"
      />
      <a-input
        v-if="needsValue(entry.condition.cmp)"
        :value="(entry.condition.value as string | undefined) ?? ''"
        size="small"
        placeholder="值"
        class="value-input"
        @change="onValueInput(entry.condition, $event)"
      />
      <a-button type="text" size="small" danger @click="removeAt(entry.index)">
        <template #icon><DeleteOutlined /></template>
      </a-button>
    </div>

    <div v-if="hasNested" class="nested-tip">
      <a-tag color="orange">嵌套条件组</a-tag>
      <span class="text-muted">当前界面只编辑扁平条件；嵌套组保留原配置，可在 JSON 中调整</span>
    </div>

    <a-button type="dashed" block size="small" @click="addCondition">
      <template #icon><PlusOutlined /></template>
      添加条件
    </a-button>
  </div>
</template>

<style scoped lang="scss">
.condition-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.op-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.condition-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.field-select {
  flex: 1 1 auto;
  min-width: 0;
}

.cmp-select {
  flex: 0 0 100px;
}

.value-input {
  flex: 0 0 120px;
}

.nested-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
}
</style>

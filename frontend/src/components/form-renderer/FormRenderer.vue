<script setup lang="ts">
/**
 * 通用表单渲染器（PRD §5「配置器均以…实时预览」，F1.4）。
 *
 * **单一渲染树，三种态由状态表驱动**（决策 D3）：
 *   编辑态（发起填写/预览交互）、只读态（审批查看）、权限态（M3 由服务端下发的矩阵）
 * 都走同一套代码，不做分叉实现 —— 否则「发起页看起来对、审批页看起来错」这类问题
 * 会反复出现。
 *
 * 被四处复用：发起页（M4）、实例详情（M4）、快照回放（M4）、设计器预览（M2）。
 *
 * 公式（决策 D4）：这里只做**即时显示**，提交时服务端会重算覆盖。
 */
import { computed } from 'vue'

import SectionBlock from '@/components/form-renderer/SectionBlock.vue'
import { resolveFieldStates } from '@/components/form-renderer/useFieldState'
import type { FormSchema } from '@/types/form'
import { evaluateSchemaFormulas } from '@/utils/formula'

const props = withDefaults(
  defineProps<{
    schema: FormSchema
    modelValue: Record<string, unknown>
    mode?: 'edit' | 'readonly' | 'preview'
    /** 没有任何可见字段时的提示语 */
    emptyText?: string
  }>(),
  { mode: 'edit', emptyText: '该表单还没有配置字段' },
)

const emit = defineEmits<{ 'update:modelValue': [Record<string, unknown>] }>()

const mode = computed(() => props.mode ?? 'edit')

const states = computed(() => resolveFieldStates(props.schema, mode.value))

/** 前端即时重算的公式结果。提交时服务端会再算一遍并覆盖。 */
const computedValues = computed(() => {
  if (!props.schema.sections?.length) return {}
  return evaluateSchemaFormulas(props.schema, props.modelValue)
})

/**
 * 传给分区/控件的值 = 用户输入 + 算好的公式值。
 * 子表用重算后的行，这样行内「小计」列在只读态也有值。
 */
const displayValues = computed<Record<string, unknown>>(() => ({
  ...props.modelValue,
  ...computedValues.value,
}))

const hasVisibleField = computed(() =>
  props.schema.sections?.some((section) =>
    section.fields.some((f) => states.value[f.key]?.visible),
  ),
)

function onValueChange(key: string, value: unknown): void {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<template>
  <div class="form-renderer">
    <template v-if="hasVisibleField">
      <SectionBlock
        v-for="section in schema.sections"
        :key="section.key"
        :section="section"
        :values="displayValues"
        :states="states"
        :mode="mode"
        :formula-values="computedValues"
        @update:value="onValueChange"
      />
    </template>

    <a-empty v-else :description="emptyText" />
  </div>
</template>

<style scoped>
.form-renderer {
  width: 100%;
}
</style>

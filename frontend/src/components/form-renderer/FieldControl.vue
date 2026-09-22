<script setup lang="ts">
/**
 * 单个字段的渲染入口：按 `field.type` 分派到具体控件。
 *
 * **三态由 `state` 驱动，不在这里判断权限**（决策 D3）：
 *   - `state.visible === false` → 调用方已经跳过（这里再兜一层）
 *   - `state.editable === false` → 走只读展示分支
 *   - 否则 → 渲染可交互控件
 *
 * 简单标量控件内联在此；人员/部门、附件、子表、级联因为逻辑较重单独成组件。
 */
import dayjs, { type Dayjs } from 'dayjs'
import { computed } from 'vue'

import AttachmentControl from '@/components/form-renderer/controls/AttachmentControl.vue'
import CascaderControl from '@/components/form-renderer/controls/CascaderControl.vue'
import OrgPickerControl from '@/components/form-renderer/controls/OrgPickerControl.vue'
import SubtableControl from '@/components/form-renderer/controls/SubtableControl.vue'
import type { FieldDef, FieldState } from '@/types/form'
import { evaluateFormula } from '@/utils/formula'
import { formatValue } from '@/utils/formValue'

const props = withDefaults(
  defineProps<{
    field: FieldDef
    modelValue: unknown
    state: FieldState
    mode: 'edit' | 'readonly' | 'preview'
    /** 子表行内使用，间距更紧凑 */
    compact?: boolean
    /** 公式字段在只读态下的取值来源（由父级传入已算好的值） */
    computedValue?: unknown
    /** 同层的其他字段值，级联下拉要靠它读父字段（子表内传所在行） */
    values?: Record<string, unknown>
  }>(),
  { compact: false, computedValue: undefined, values: () => ({}) },
)

const emit = defineEmits<{ 'update:modelValue': [unknown] }>()

const editable = computed(() => props.state.editable && props.mode === 'edit')
const label = computed(() => props.field.label)

function set(value: unknown): void {
  emit('update:modelValue', value ?? null)
}

// --------------------------------------------------------------------------- 日期时间
// antd 的 Picker 用 dayjs 对象，库里的值是字符串 —— 两边都要转。

function toDayjs(value: unknown): Dayjs | undefined {
  if (value === null || value === undefined || value === '') return undefined
  const parsed = dayjs(String(value))
  return parsed.isValid() ? parsed : undefined
}

function fromDayjs(value: unknown): string | null {
  const d = value as Dayjs | null | undefined
  if (!d) return null
  if (props.field.type === 'date') return d.format('YYYY-MM-DD')
  if (props.field.type === 'time') return d.format('HH:mm:ss')
  return d.format('YYYY-MM-DD HH:mm:ss')
}

const dateValue = computed(() => toDayjs(props.modelValue))

// --------------------------------------------------------------------------- 只读展示

const readonlyText = computed(() => {
  if (props.field.type === 'formula') {
    const value =
      props.computedValue !== undefined
        ? props.computedValue
        : evaluateFormula(props.field.formula ?? { type: 'arithmetic' }, {})
    return value === null || value === undefined ? '—' : String(value)
  }
  return formatValue(props.field, props.modelValue)
})

// --------------------------------------------------------------------------- 选项

const options = computed(() =>
  (props.field.options ?? []).map((o) => ({ label: o.label, value: o.value })),
)
</script>

<template>
  <template v-if="!state.visible"></template>

  <!-- 只读 / 预览 -->
  <span v-else-if="!editable" class="readonly-value">{{ readonlyText }}</span>

  <!-- 单行文本 -->
  <a-input
    v-else-if="field.type === 'text'"
    :value="(modelValue as string | undefined) ?? ''"
    :placeholder="field.placeholder || `请输入${label}`"
    :maxlength="field.validators?.max_length ?? undefined"
    allow-clear
    @update:value="set"
  />

  <!-- 多行文本 -->
  <a-textarea
    v-else-if="field.type === 'textarea'"
    :value="(modelValue as string | undefined) ?? ''"
    :placeholder="field.placeholder || `请输入${label}`"
    :maxlength="field.validators?.max_length ?? undefined"
    :rows="compact ? 2 : 3"
    show-count
    @update:value="set"
  />

  <!-- 数字 -->
  <a-input-number
    v-else-if="field.type === 'number'"
    :value="(modelValue as number | null)"
    :placeholder="field.placeholder || `请输入${label}`"
    :min="field.validators?.min ?? undefined"
    :max="field.validators?.max ?? undefined"
    :precision="field.validators?.precision ?? undefined"
    style="width: 100%"
    @update:value="set"
  />

  <!-- 单选 -->
  <a-radio-group
    v-else-if="field.type === 'radio'"
    :value="modelValue"
    :options="options"
    @update:value="set"
  />

  <!-- 复选 -->
  <a-checkbox-group
    v-else-if="field.type === 'checkbox'"
    :value="(modelValue as Array<string | number> | undefined) ?? []"
    :options="options"
    @update:value="set"
  />

  <!-- 下拉 -->
  <a-select
    v-else-if="field.type === 'select'"
    :value="(modelValue as string | number | undefined)"
    :options="options"
    :placeholder="field.placeholder || `请选择${label}`"
    allow-clear
    show-search
    option-filter-prop="label"
    style="width: 100%"
    @update:value="set"
  />

  <!-- 日期 / 时间 / 日期时间 -->
  <a-date-picker
    v-else-if="field.type === 'date'"
    :value="dateValue"
    :placeholder="field.placeholder || '请选择日期'"
    style="width: 100%"
    @update:value="set(fromDayjs($event as Dayjs | null))"
  />

  <a-time-picker
    v-else-if="field.type === 'time'"
    :value="dateValue"
    :placeholder="field.placeholder || '请选择时间'"
    style="width: 100%"
    @update:value="set(fromDayjs($event as Dayjs | null))"
  />

  <a-date-picker
    v-else-if="field.type === 'datetime'"
    :value="dateValue"
    :show-time="{ format: 'HH:mm' }"
    :placeholder="field.placeholder || '请选择日期时间'"
    format="YYYY-MM-DD HH:mm"
    style="width: 100%"
    @update:value="set(fromDayjs($event as Dayjs | null))"
  />

  <!-- 开关 -->
  <a-switch
    v-else-if="field.type === 'switch'"
    :checked="Boolean(modelValue)"
    @update:checked="set"
  />

  <!-- 人员 / 部门 -->
  <OrgPickerControl
    v-else-if="['user', 'user_multi', 'dept', 'dept_multi'].includes(field.type)"
    :field="field"
    :model-value="modelValue"
    :editable="editable"
    @update:model-value="set"
  />

  <!-- 附件 / 图片 -->
  <AttachmentControl
    v-else-if="field.type === 'attachment' || field.type === 'image'"
    :field="field"
    :model-value="modelValue"
    :editable="editable"
    @update:model-value="set"
  />

  <!-- 子表 -->
  <SubtableControl
    v-else-if="field.type === 'subtable'"
    :field="field"
    :model-value="modelValue"
    :editable="editable"
    @update:model-value="set"
  />

  <!-- 级联下拉 -->
  <CascaderControl
    v-else-if="field.type === 'cascader'"
    :field="field"
    :model-value="modelValue"
    :editable="editable"
    :values="values"
    @update:model-value="set"
  />

  <!-- 公式字段：只读展示算出来的值 -->
  <span v-else-if="field.type === 'formula'" class="readonly-value formula-value">
    {{ readonlyText }}
  </span>

  <a-input v-else :value="(modelValue as string | undefined) ?? ''" @update:value="set" />
</template>

<style scoped>
.readonly-value {
  display: inline-block;
  min-height: 22px;
  white-space: pre-wrap;
  word-break: break-word;
}

.formula-value {
  font-weight: 600;
  color: #1677ff;
}
</style>

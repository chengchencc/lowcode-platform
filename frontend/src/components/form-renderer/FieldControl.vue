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
import { computed, onMounted } from 'vue'

import AttachmentControl from '@/components/form-renderer/controls/AttachmentControl.vue'
import CascaderControl from '@/components/form-renderer/controls/CascaderControl.vue'
import OrgPickerControl from '@/components/form-renderer/controls/OrgPickerControl.vue'
import SubtableControl from '@/components/form-renderer/controls/SubtableControl.vue'
import { useOrgStore } from '@/stores/org'
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

const org = useOrgStore()

/** 控件是否真正可交互：必须同时 state.editable + mode=edit */
const editable = computed(() => props.state.editable && props.mode === 'edit')
/** 控件是否要渲染成「只读外观」（不可交互但保持正常视觉） */
const viewMode = computed(() => !editable.value)
/** 这些控件用 disabled 属性来禁用交互，然后 CSS 覆盖禁用态样式 */
const disableInteraction = computed(() => viewMode.value && !['radio', 'checkbox', 'switch'].includes(props.field.type))
const label = computed(() => props.field.label)
/** 附件/图片即使只读也要由专门控件渲染，才能点开下载和显示缩略图 */
const isFileField = computed(() =>
  ['attachment', 'image'].includes(props.field.type),
)

onMounted(() => {
  // 只读态不经过 OrgPickerControl（它在可编辑时才挂载），部门 id 换名字要先有部门树
  if (props.field.type.startsWith('dept')) void org.loadDeptTree()
})

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
  // 人员/部门的值是 id，只读展示必须换成名字（否则就是一个 #1）
  return formatValue(props.field, props.modelValue, (kind, id) => {
    const numeric = Number(id)
    return kind === 'dept' ? org.deptName(numeric) : org.userName(numeric)
  })
})

// --------------------------------------------------------------------------- 选项

const options = computed(() =>
  (props.field.options ?? []).map((o) => ({ label: o.label, value: o.value })),
)
</script>

<template>
  <!-- 单行文本 -->
  <template v-if="field.type === 'text'">
    <span v-if="viewMode" class="text-readonly">{{ (modelValue as string | undefined) ?? '—' }}</span>
    <a-input
      v-else
      :value="(modelValue as string | undefined) ?? ''"
      :placeholder="field.placeholder || `请输入${label}`"
      :maxlength="field.validators?.max_length ?? undefined"
      allow-clear
      @update:value="set"
    />
  </template>

  <!-- 多行文本 -->
  <template v-else-if="field.type === 'textarea'">
    <span v-if="viewMode" class="textarea-readonly">{{ (modelValue as string | undefined) || '—' }}</span>
    <a-textarea
      v-else
      :value="(modelValue as string | undefined) ?? ''"
      :placeholder="field.placeholder || `请输入${label}`"
      :maxlength="field.validators?.max_length ?? undefined"
      :rows="compact ? 2 : 3"
      show-count
      @update:value="set"
    />
  </template>

  <!-- 数字 -->
  <a-input-number
    v-else-if="field.type === 'number'"
    :value="(modelValue as number | null)"
    :placeholder="field.placeholder || `请输入${label}`"
    :min="field.validators?.min ?? undefined"
    :max="field.validators?.max ?? undefined"
    :precision="field.validators?.precision ?? undefined"
    :disabled="disableInteraction"
    class="view-control"
    style="width: 100%"
    @update:value="set"
  />

  <!-- 单选：保持正常视觉 + pointer-events: none，不要用 disabled -->
  <a-radio-group
    v-else-if="field.type === 'radio'"
    :value="modelValue"
    :options="options"
    :class="{ 'pointer-none': viewMode }"
    @update:value="set"
  />

  <!-- 复选：保持正常视觉 + pointer-events: none -->
  <a-checkbox-group
    v-else-if="field.type === 'checkbox'"
    :value="(modelValue as Array<string | number> | undefined) ?? []"
    :options="options"
    :class="{ 'pointer-none': viewMode }"
    @update:value="set"
  />

  <!-- 下拉 -->
  <a-select
    v-else-if="field.type === 'select'"
    :value="(modelValue as string | number | undefined)"
    :options="options"
    :placeholder="field.placeholder || `请选择${label}`"
    :disabled="disableInteraction"
    allow-clear
    show-search
    option-filter-prop="label"
    class="view-control"
    style="width: 100%"
    @update:value="set"
  />

  <!-- 日期 / 时间 / 日期时间：只读态用文本显示，编辑态才用 picker -->
  <template v-else-if="field.type === 'date' || field.type === 'time' || field.type === 'datetime'">
    <span v-if="viewMode" class="date-readonly">{{ readonlyText || '—' }}</span>
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
      v-else
      :value="dateValue"
      :show-time="{ format: 'HH:mm' }"
      :placeholder="field.placeholder || '请选择日期时间'"
      format="YYYY-MM-DD HH:mm"
      style="width: 100%"
      @update:value="set(fromDayjs($event as Dayjs | null))"
    />
  </template>

  <!-- 开关：disabled 态视觉差异大，也用 pointer-events -->
  <a-switch
    v-else-if="field.type === 'switch'"
    :checked="Boolean(modelValue)"
    :class="{ 'pointer-none': viewMode }"
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

  <!-- 公式字段：展示算出来的值 -->
  <span v-else-if="field.type === 'formula'" class="readonly-value formula-value">
    {{ readonlyText }}
  </span>

  <a-input v-else :value="(modelValue as string | undefined) ?? ''" :readonly="viewMode" class="view-input" @update:value="set" />
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

/**
 * 只读态保持正常控件外观，只是不可交互。
 * 两种实现：
 *   1) :readonly 属性（a-input / a-textarea / a-input-number）
 *   2) :disabled 属性（a-select / a-date-picker）但用 CSS 覆盖禁用态样式
 */

/* pointer-events: none 替代 disabled —— radio/checkbox/switch 的 disabled 视觉差异太大 */
.pointer-none {
  pointer-events: none;
  user-select: none;
}

/* disabled 控件：覆盖 Ant Design Vue 禁用态的灰背景、透明度过高、边框色 */
.view-control :deep(.ant-select-disabled),
.view-control :deep(.ant-input-disabled),
.view-control :deep(.ant-input-number-disabled),
.view-control :deep(.ant-picker-disabled) {
  background: #fff !important;
  opacity: 1 !important;
  color: rgba(0, 0, 0, 0.88) !important;
  border-color: #d9d9d9 !important;
}

/* date-picker 的后缀图标也别灰 */
.view-control :deep(.ant-picker-suffix),
.view-control :deep(.ant-picker-clear) {
  color: rgba(0, 0, 0, 0.45) !important;
}

/* input-number 的加减按钮 */
.view-control :deep(.ant-input-number-handler-wrap) {
  opacity: 1 !important;
  pointer-events: none;
}

/* readonly 的 input/textarea：保持正常边框和背景 */
.view-input :deep(.ant-input),
.view-input :deep(.ant-input-affix-wrapper),
.view-input :deep(.ant-input-textarea textarea) {
  background: #fff;
  border-color: #d9d9d9;
}

/* 日期/时间只读态、单行文本只读态：单行输入框样式 */
.date-readonly,
.text-readonly {
  display: inline-block;
  width: 100%;
  min-height: 32px;
  padding: 4px 11px;
  color: rgba(0, 0, 0, 0.88);
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  line-height: 22px;
  box-sizing: border-box;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 多行文本只读态：textarea 样式 */
.textarea-readonly {
  display: inline-block;
  width: 100%;
  min-height: 80px;
  padding: 5px 11px;
  color: rgba(0, 0, 0, 0.88);
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  line-height: 1.5715;
  box-sizing: border-box;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

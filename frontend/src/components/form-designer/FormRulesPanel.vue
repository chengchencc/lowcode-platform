<script setup lang="ts">
/**
 * 表单联动规则面板（M9）。
 *
 * 规则只收紧权限：hidden / readonly / required。后端发布校验负责引用完整性
 * 与循环依赖；这里提供可视化的条件与效果编辑。
 */
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'

import ConditionEditor from '@/components/form-designer/ConditionEditor.vue'
import type { Condition, ConditionGroup } from '@/types/conditions'
import { isConditionGroup } from '@/types/conditions'
import type { FormRule, FormSchema, RuleEffectType } from '@/types/form'
import { isDisplayField } from '@/types/form'

const props = defineProps<{
  schema: FormSchema
  rules: FormRule[]
}>()

const emit = defineEmits<{ change: [] }>()

const fieldOptions = computed<Array<{ value: string; label: string }>>(() => {
  const out: Array<{ value: string; label: string }> = []
  for (const section of props.schema.sections) {
    for (const field of section.fields) {
      if (isDisplayField(field)) continue
      out.push({ value: field.key, label: `${field.label}（${field.key}）` })
    }
  }
  return out
})

const effectOptions: Array<{ value: RuleEffectType; label: string }> = [
  { value: 'hidden', label: '隐藏' },
  { value: 'readonly', label: '只读' },
  { value: 'required', label: '必填' },
]

function notify(): void {
  emit('change')
}

function conditionKeys(group: ConditionGroup): Set<string> {
  const out = new Set<string>()
  const walk = (current: ConditionGroup): void => {
    for (const item of current.conditions) {
      if (isConditionGroup(item)) walk(item)
      else out.add((item as Condition).field)
    }
  }
  walk(group)
  return out
}

function targetOptions(rule: FormRule): Array<{ value: string; label: string }> {
  const used = conditionKeys(rule.when)
  return fieldOptions.value.filter((option) => !used.has(option.value))
}

function targetInvalid(rule: FormRule, target: string): boolean {
  return conditionKeys(rule.when).has(target)
}

const invalidTargetCount = computed(() =>
  props.rules.reduce(
    (count, rule) =>
      count + rule.effects.filter((effect) => targetInvalid(rule, effect.target)).length,
    0,
  ),
)

function nextRuleId(): string {
  const used = new Set(props.rules.map((rule) => rule.id))
  let n = 1
  while (used.has(`r${n}`)) n += 1
  return `r${n}`
}

function addRule(): void {
  const first = fieldOptions.value[0]?.value ?? ''
  // 默认目标避开条件字段与标题字段，减少一建规则就自引用/误伤标题的情况
  const target =
    fieldOptions.value.find(
      (option) => option.value !== first && option.value !== props.schema.title_field,
    )?.value
    ?? fieldOptions.value.find((option) => option.value !== first)?.value
    ?? first
  props.rules.push({
    id: nextRuleId(),
    name: `规则 ${props.rules.length + 1}`,
    when: {
      op: 'and',
      conditions: first ? [{ field: first, cmp: '==', value: '' }] : [],
    },
    effects: target ? [{ target, effect: 'hidden' }] : [],
    clear_when_hidden: false,
  })
  notify()
}

function removeRule(index: number): void {
  props.rules.splice(index, 1)
  notify()
}

function addEffect(rule: FormRule): void {
  rule.effects.push({
    target: fieldOptions.value[0]?.value ?? '',
    effect: 'hidden',
  })
  notify()
}

function removeEffect(rule: FormRule, index: number): void {
  rule.effects.splice(index, 1)
  notify()
}

function fieldLabel(key: string): string {
  return fieldOptions.value.find((item) => item.value === key)?.label ?? key
}

function fixInvalidTargets(): void {
  for (const rule of props.rules) {
    const used = conditionKeys(rule.when)
    const fallback =
      fieldOptions.value.find(
        (option) => !used.has(option.value) && option.value !== props.schema.title_field,
      )?.value
      ?? fieldOptions.value.find((option) => !used.has(option.value))?.value
    if (!fallback) continue
    for (const effect of rule.effects) {
      if (used.has(effect.target)) effect.target = fallback
    }
  }
  notify()
}

function onConditionChange(rule: FormRule): void {
  // 条件字段变了以后，原本的目标可能变成了「目标 == 条件字段」的自引用。
  // 自动换到第一个不与条件冲突的字段，避免规则静默失效。
  const used = conditionKeys(rule.when)
  const fallback =
    fieldOptions.value.find(
      (option) => !used.has(option.value) && option.value !== props.schema.title_field,
    )?.value
    ?? fieldOptions.value.find((option) => !used.has(option.value))?.value
  if (fallback) {
    for (const effect of rule.effects) {
      if (used.has(effect.target)) effect.target = fallback
    }
  }
  notify()
}
</script>

<template>
  <div class="rules-panel">
    <a-alert
      type="info"
      show-icon
      class="tip"
      message="规则只收紧权限：节点权限已经隐藏的字段不会被规则点亮；同一字段命中多条规则时，隐藏 > 只读 > 必填。"
    />

    <a-alert
      v-if="invalidTargetCount"
      type="warning"
      show-icon
      class="tip"
      :message="`有 ${invalidTargetCount} 个目标与规则条件字段相同；这种规则不会影响其他字段，请改选目标。`"
    >
      <template #action>
        <a-button size="small" @click="fixInvalidTargets">自动修正</a-button>
      </template>
    </a-alert>

    <a-empty v-if="!rules.length" description="还没有联动规则" />

    <div v-for="(rule, index) in rules" :key="rule.id" class="rule-card">
      <div class="rule-head">
        <a-input
          v-model:value="rule.name"
          size="small"
          placeholder="规则名称"
          class="rule-name"
          @change="notify"
        />
        <a-tag class="rule-id">{{ rule.id }}</a-tag>
        <span class="spacer" />
        <a-button type="text" size="small" danger @click="removeRule(index)">
          <template #icon><DeleteOutlined /></template>
          删除规则
        </a-button>
      </div>

      <div class="rule-block">
        <div class="block-title">当满足</div>
        <ConditionEditor
          :group="rule.when"
          :field-options="fieldOptions"
          @change="onConditionChange(rule)"
        />
      </div>

      <div class="rule-block">
        <div class="block-title">则</div>
        <div v-for="(effect, eidx) in rule.effects" :key="eidx" class="effect-row">
          <a-select
            v-model:value="effect.target"
            :options="targetOptions(rule)"
            size="small"
            placeholder="目标字段"
            show-search
            option-filter-prop="label"
            class="effect-target"
            @change="notify"
          />
          <a-select
            v-model:value="effect.effect"
            :options="effectOptions"
            size="small"
            class="effect-type"
            @change="notify"
          />
          <a-tag v-if="targetInvalid(rule, effect.target)" color="red">不能用条件字段</a-tag>
          <span v-else class="text-muted effect-hint">{{ fieldLabel(effect.target) }}</span>
          <a-button type="text" size="small" danger @click="removeEffect(rule, eidx)">
            <template #icon><DeleteOutlined /></template>
          </a-button>
        </div>
        <a-button type="dashed" block size="small" @click="addEffect(rule)">
          <template #icon><PlusOutlined /></template>
          添加效果
        </a-button>
        <a-checkbox v-model:checked="rule.clear_when_hidden" @change="notify">
          隐藏时清空该字段的值
        </a-checkbox>
      </div>
    </div>

    <a-button type="primary" block @click="addRule">
      <template #icon><PlusOutlined /></template>
      添加规则
    </a-button>
  </div>
</template>

<style scoped lang="scss">
.rules-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tip {
  margin-bottom: 4px;
}

.rule-card {
  padding: 10px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fafafa;
}

.rule-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.rule-name {
  width: 220px;
}

.rule-id {
  font-family: monospace;
  font-size: 11px;
}

.spacer {
  flex: 1;
}

.rule-block {
  margin-bottom: 10px;
}

.block-title {
  margin-bottom: 6px;
  color: rgba(0, 0, 0, 0.55);
  font-size: 12px;
  font-weight: 600;
}

.effect-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.effect-target {
  flex: 1 1 auto;
  min-width: 0;
}

.effect-type {
  flex: 0 0 90px;
}

.effect-hint {
  flex: 0 0 auto;
  font-size: 11px;
}
</style>

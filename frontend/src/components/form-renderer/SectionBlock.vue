<script setup lang="ts">
/**
 * 一个分区的渲染（PRD §3.4 机制 B）。
 *
 * 分区带**阶段标签**：申请区 / 审批区 / 补充区 / 归档区。
 * 分区内字段全部隐藏时整块不渲染 —— 这就是「财务的补充字段在申请阶段完全不可见」
 * 的实现方式，而不是把每个字段留一个空位。
 */
import { computed } from 'vue'

import FieldControl from '@/components/form-renderer/FieldControl.vue'
import { STAGE_COLORS, sectionHasVisibleField, type FieldState } from '@/components/form-renderer/useFieldState'
import type { SectionDef } from '@/types/form'
import { SECTION_STAGE_LABELS } from '@/types/form'

const props = defineProps<{
  section: SectionDef
  values: Record<string, unknown>
  states: Record<string, FieldState>
  mode: 'edit' | 'readonly' | 'preview'
  /**
   * 公式字段的已算结果，由父级统一重算后传下来。
   * 名字不能叫 `computed` —— 那会遮蔽 Vue 的 `computed()`，模板里就用不了了。
   */
  formulaValues?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:value': [key: string, value: unknown] }>()

const visible = computed(() => sectionHasVisibleField(props.section, props.states))

const visibleFields = computed(() =>
  props.section.fields.filter((f) => props.states[f.key]?.visible),
)

const stage = computed(() => props.section.stage ?? 'apply')

const columns = computed(() => {
  // 子表和附件这类「宽字段」独占一行，否则挤在一起没法看
  const wide = new Set(['subtable', 'textarea', 'attachment', 'image'])
  return props.section.fields.length && props.section.fields.every((f) => wide.has(f.type))
    ? 1
    : 2
})

function stateOf(key: string): FieldState {
  return props.states[key] ?? { visible: true, editable: false, required: false }
}
</script>

<template>
  <a-card v-if="visible" :bordered="false" class="section-block" :body-style="{ paddingTop: '12px' }">
    <template #title>
      <span class="section-title">
        {{ section.title }}
        <a-tag :color="STAGE_COLORS[stage]" class="stage-tag">
          {{ SECTION_STAGE_LABELS[stage] }}
        </a-tag>
      </span>
    </template>

    <p v-if="section.description" class="text-muted section-desc">{{ section.description }}</p>

    <a-row :gutter="16">
      <a-col
        v-for="field in visibleFields"
        :key="field.key"
        :xs="24"
        :md="['subtable', 'textarea', 'attachment', 'image'].includes(field.type) ? 24 : 24 / columns"
      >
        <a-form-item
          :label="field.label"
          :required="stateOf(field.key).required"
          :help="field.help || undefined"
          :validate-status="undefined"
        >
          <FieldControl
            :field="field"
            :model-value="values[field.key]"
            :state="stateOf(field.key)"
            :mode="mode"
            :computed-value="formulaValues?.[field.key]"
            :values="values"
            @update:model-value="(v) => emit('update:value', field.key, v)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </a-card>
</template>

<style scoped lang="scss">
.section-block {
  margin-bottom: 16px;
  background: #fff;
  border-radius: 8px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.stage-tag {
  font-size: 11px;
  font-weight: normal;
}

.section-desc {
  margin: 0 0 12px;
  font-size: 12px;
}
</style>

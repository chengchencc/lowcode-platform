<script setup lang="ts">
/**
 * 一个分区的渲染（PRD §3.4 机制 B）。
 *
 * 分区带**阶段标签**：申请区 / 审批区 / 补充区 / 归档区。
 * 分区内字段全部隐藏时整块不渲染 —— 这就是「财务的补充字段在申请阶段完全不可见」
 * 的实现方式，而不是把每个字段留一个空位。
 */
import { DownOutlined, RightOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'

import DisplayBlock from '@/components/form-renderer/DisplayBlock.vue'
import FieldControl from '@/components/form-renderer/FieldControl.vue'
import { STAGE_COLORS, sectionHasVisibleField, type FieldState } from '@/components/form-renderer/useFieldState'
import type { FieldDef, FormLayout, SectionDef } from '@/types/form'
import { SECTION_STAGE_LABELS, isDisplayField } from '@/types/form'

const props = defineProps<{
  section: SectionDef
  values: Record<string, unknown>
  states: Record<string, FieldState>
  mode: 'edit' | 'readonly' | 'preview'
  /** 表单级布局；分区 columns 缺省时跟随它 */
  layout?: FormLayout | null
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
const collapsed = ref(false)

/** 分区列数：分区覆盖 > 表单默认 > 2 */
const columns = computed(() =>
  Math.min(4, Math.max(1, props.section.columns ?? props.layout?.columns ?? 2)),
)

/** 这些控件默认独占一行 */
const WIDE_TYPES = new Set(['subtable', 'textarea', 'attachment', 'image'])

function spanOf(field: FieldDef): number {
  const auto = isDisplayField(field) || WIDE_TYPES.has(field.type)
    ? 24
    : Math.floor(24 / columns.value)
  const span = field.span ?? auto
  return Math.min(24, Math.max(1, span))
}

function stateOf(key: string): FieldState {
  return props.states[key] ?? { visible: true, editable: false, required: false }
}
</script>

<template>
  <a-card v-if="visible" :bordered="false" class="section-block" :body-style="{ paddingTop: '12px' }">
    <template #title>
      <span class="section-title">
        <button
          v-if="section.collapsible"
          type="button"
          class="collapse-btn"
          :title="collapsed ? '展开分区' : '折叠分区'"
          @click.stop="collapsed = !collapsed"
        >
          <RightOutlined v-if="collapsed" />
          <DownOutlined v-else />
        </button>
        {{ section.title }}
        <a-tag :color="STAGE_COLORS[stage]" class="stage-tag">
          {{ SECTION_STAGE_LABELS[stage] }}
        </a-tag>
      </span>
    </template>

    <template v-if="!collapsed">
      <p v-if="section.description" class="text-muted section-desc">{{ section.description }}</p>

      <a-row :gutter="16">
        <a-col
          v-for="field in visibleFields"
          :key="field.key"
          :xs="24"
          :md="spanOf(field)"
        >
          <DisplayBlock v-if="isDisplayField(field)" :field="field" />
          <a-form-item
            v-else
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
    </template>
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

.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: rgba(0, 0, 0, 0.45);
  cursor: pointer;

  &:hover {
    background: #f0f0f0;
    color: #1677ff;
  }
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

<script setup lang="ts">
/**
 * 字段权限矩阵配置（PRD §3.4 机制 A / 机制 B）。
 *
 * 分三层暴露给设计者，对应引擎的求值顺序：
 *   L1 `base` + `partitions` —— 按分区批量设模板（机制 B）
 *   L2 `overrides`          —— 单字段覆盖（机制 A）
 *   L3 `conditional_overrides` —— 条件覆盖
 *
 * 界面上**按分区折叠**而不是平铺全部字段：一个报销单可能有几十个字段，
 * 平铺会淹没真正要配的那几个。分区的阶段标签也一并显示 ——
 * 那是机制 B 默认值的来源，设计者需要看到它才能理解「为什么这里是隐藏」。
 */
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'

import type { FieldDef, FormSchema, SectionDef } from '@/types/form'
import { SECTION_STAGE_LABELS } from '@/types/form'
import type { FieldPermissionRule, PermMode } from '@/types/flow'
import { PERM_MODE_COLORS, PERM_MODE_LABELS } from '@/types/flow'

const props = defineProps<{
  rule: FieldPermissionRule
  formSchema: FormSchema | null
}>()

const emit = defineEmits<{ change: [] }>()

const MODE_OPTIONS = (Object.keys(PERM_MODE_LABELS) as PermMode[]).map((m) => ({
  value: m,
  label: PERM_MODE_LABELS[m],
}))

const sections = computed<SectionDef[]>(() => props.formSchema?.sections ?? [])

function notify(): void {
  emit('change')
}

/** 子表列的引用记法，与服务端 permissions.column_ref 一致 */
function columnRef(subtableKey: string, columnKey: string): string {
  return `${subtableKey}[].${columnKey}`
}

/** 该字段当前生效的模式（分区批量 → 单字段覆盖，未命中则回落到 base） */
function effectiveMode(sectionKey: string, fieldKey: string): PermMode {
  const override = props.rule.overrides?.[fieldKey]
  if (override) return override
  const byPartition = props.rule.partitions?.[sectionKey]
  if (byPartition) return byPartition
  return props.rule.base
}

function effectiveSource(sectionKey: string, fieldKey: string): string {
  if (props.rule.overrides?.[fieldKey]) return '单字段覆盖'
  if (props.rule.partitions?.[sectionKey]) return '分区批量'
  return '默认'
}

function setPartition(sectionKey: string, mode: PermMode | undefined): void {
  if (!props.rule.partitions) props.rule.partitions = {}
  if (mode === undefined) {
    delete props.rule.partitions[sectionKey]
  } else {
    props.rule.partitions[sectionKey] = mode
  }
  notify()
}

function setOverride(fieldKey: string, mode: PermMode | undefined): void {
  if (!props.rule.overrides) props.rule.overrides = {}
  if (mode === undefined) {
    delete props.rule.overrides[fieldKey]
  } else {
    props.rule.overrides[fieldKey] = mode
  }
  notify()
}

/** 计算字段（公式）永不接受输入，界面上标注出来避免设计者白配 */
function isComputed(field: FieldDef): boolean {
  return field.type === 'formula'
}

/** 一次性清空全部覆盖（回到「只由分区批量决定」的状态） */
function clearOverrides(): void {
  props.rule.overrides = {}
  notify()
}

const overrideCount = computed(() => Object.keys(props.rule.overrides ?? {}).length)
const partitionCount = computed(() => Object.keys(props.rule.partitions ?? {}).length)
</script>

<template>
  <div class="perm-panel">
    <a-alert type="info" show-icon class="tip">
      <template #message>求值顺序：分区批量 → 单字段覆盖 → 条件覆盖（后者覆盖前者）</template>
      <template #description>
        <span class="text-muted">
          未列出的分区用「默认」模式。补充字段通常应保持「隐藏」，由本节点显式打开。
        </span>
      </template>
    </a-alert>

    <!-- ---------------- L1 默认模式 ---------------- -->
    <a-form layout="vertical" size="small">
      <a-form-item label="默认模式（未单独设置的分区）">
        <a-select v-model:value="rule.base" :options="MODE_OPTIONS" @change="notify" />
      </a-form-item>
    </a-form>

    <!-- ---------------- L1 分区批量 ---------------- -->
    <div class="section-block">
      <div class="block-head">
        <span class="block-title">按分区设置</span>
        <span class="text-muted small">{{ partitionCount }} 个分区已覆盖</span>
      </div>

      <div v-for="section in sections" :key="section.key" class="row">
        <div class="row-label">
          <span>{{ section.title }}</span>
          <a-tag class="stage-tag">{{ SECTION_STAGE_LABELS[section.stage ?? 'apply'] }}</a-tag>
        </div>
        <a-select
          :value="rule.partitions?.[section.key]"
          :options="MODE_OPTIONS"
          :placeholder="`默认（${PERM_MODE_LABELS[rule.base]}）`"
          size="small"
          allow-clear
          class="row-control"
          @change="(v: PermMode | undefined) => setPartition(section.key, v)"
        />
      </div>
    </div>

    <!-- ---------------- L2 单字段覆盖 ---------------- -->
    <div class="section-block">
      <div class="block-head">
        <span class="block-title">单字段覆盖</span>
        <a v-if="overrideCount" class="text-muted small" @click="clearOverrides">
          清空 {{ overrideCount }} 项
        </a>
      </div>

      <a-collapse ghost size="small">
        <a-collapse-panel v-for="section in sections" :key="section.key">
          <template #header>
            <span>{{ section.title }}</span>
            <span class="text-muted small">（{{ section.fields.length }} 个字段）</span>
          </template>

          <div v-for="field in section.fields" :key="field.key" class="row">
            <div class="row-label">
              <span>{{ field.label }}</span>
              <a-tag v-if="isComputed(field)" color="purple" class="stage-tag">公式</a-tag>
              <span class="text-muted tiny">{{ field.key }}</span>
            </div>
            <div class="row-right">
              <a-tag :color="PERM_MODE_COLORS[effectiveMode(section.key, field.key)]" class="eff-tag">
                {{ PERM_MODE_LABELS[effectiveMode(section.key, field.key)] }}
              </a-tag>
              <a-select
                :value="rule.overrides?.[field.key]"
                :options="MODE_OPTIONS"
                :placeholder="effectiveSource(section.key, field.key)"
                size="small"
                allow-clear
                class="row-control"
                @change="(v: PermMode | undefined) => setOverride(field.key, v)"
              />
            </div>
          </div>

          <!-- 子表列 -->
          <template v-for="field in section.fields" :key="`c-${field.key}`">
            <div v-if="field.type === 'subtable' && field.columns?.length" class="columns">
              <div class="text-muted tiny column-head">子表「{{ field.label }}」的列</div>
              <div v-for="col in field.columns" :key="col.key" class="row">
                <div class="row-label indent">
                  <span>{{ col.label }}</span>
                  <a-tag v-if="isComputed(col)" color="purple" class="stage-tag">公式</a-tag>
                </div>
                <div class="row-right">
                  <a-tag
                    :color="PERM_MODE_COLORS[effectiveMode(section.key, columnRef(field.key, col.key))]"
                    class="eff-tag"
                  >
                    {{ PERM_MODE_LABELS[effectiveMode(section.key, columnRef(field.key, col.key))] }}
                  </a-tag>
                  <a-select
                    :value="rule.overrides?.[columnRef(field.key, col.key)]"
                    :options="MODE_OPTIONS"
                    :placeholder="effectiveSource(section.key, columnRef(field.key, col.key))"
                    size="small"
                    allow-clear
                    class="row-control"
                    @change="
                      (v: PermMode | undefined) => setOverride(columnRef(field.key, col.key), v)
                    "
                  />
                </div>
              </div>
            </div>
          </template>
        </a-collapse-panel>
      </a-collapse>
    </div>

    <!-- ---------------- L3 条件覆盖 ---------------- -->
    <div class="section-block">
      <div class="block-head">
        <span class="block-title">条件覆盖</span>
        <span class="text-muted small">
          满足条件时把某字段设为指定模式，如「金额 &gt; 2000 时金额只读」
        </span>
      </div>
      <div v-if="rule.conditional_overrides?.length" class="cond-list">
        <div v-for="(item, index) in rule.conditional_overrides" :key="index" class="cond-item">
          <span class="text-mono small">{{ item.field_key }}</span>
          <a-tag :color="PERM_MODE_COLORS[item.mode]" class="stage-tag">
            {{ PERM_MODE_LABELS[item.mode] }}
          </a-tag>
          <span class="text-muted small">当 {{ item.when?.conditions?.length ?? 0 }} 个条件满足时</span>
          <span class="spacer" />
          <a-button
            type="text"
            size="small"
            danger
            @click="
              () => {
                rule.conditional_overrides.splice(index, 1)
                notify()
              }
            "
          >
            <template #icon><DeleteOutlined /></template>
          </a-button>
        </div>
      </div>
      <a-alert
        v-else
        type="warning"
        show-icon
        :message="'M2 阶段条件覆盖需在流程定义 JSON 中配置'"
        description="图形化的条件覆盖编辑器排在后续里程碑"
      />
      <a-button
        type="dashed"
        block
        size="small"
        class="add-cond"
        @click="
          () => {
            if (!rule.conditional_overrides) rule.conditional_overrides = []
            rule.conditional_overrides.push({
              when: { op: 'and', conditions: [] },
              field_key: '',
              mode: 'readonly',
            })
            notify()
          }
        "
      >
        <template #icon><PlusOutlined /></template>
        添加条件覆盖
      </a-button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.perm-panel {
  :deep(.ant-alert) {
    margin-bottom: 12px;
  }
}

.tip :deep(.ant-alert-message) {
  font-size: 13px;
}

.section-block {
  margin-bottom: 18px;
}

.block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #f0f0f0;
}

.block-title {
  font-weight: 600;
  font-size: 13px;
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 3px 0;

  &:hover {
    background: #fafafa;
  }
}

.row-label {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  min-width: 0;

  &.indent {
    padding-left: 14px;
  }
}

.row-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 300px;
}

.row-control {
  width: 150px;
  flex: 0 0 150px;
}

.eff-tag {
  flex: 0 0 auto;
  margin: 0;
  font-size: 11px;
}

.stage-tag {
  font-size: 10px;
  margin: 0;
  transform: scale(0.92);
}

.small {
  font-size: 12px;
}

.tiny {
  font-size: 11px;
}

.columns {
  margin: 4px 0 8px;
  padding-left: 8px;
  border-left: 2px solid #f0f0f0;
}

.column-head {
  padding: 2px 0;
}

.cond-list {
  margin-bottom: 8px;
}

.cond-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  margin-bottom: 4px;
  border-radius: 4px;
  background: #fafafa;
  font-size: 12px;
}

.spacer {
  flex: 1;
}

.add-cond {
  margin-top: 4px;
}
</style>

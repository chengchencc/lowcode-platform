<script setup lang="ts">
/**
 * 明细子表（PRD §3.2.2，F1.6）。
 *
 * 值是一组行对象：`[{列key: 值, ...}, ...]`。
 * 行内公式列（如「小计 = 数量 × 单价」）在编辑时即时计算，提交时服务端重算覆盖。
 *
 * 只读态渲染成普通表格（PRD：发起可增删行，审批只读）。
 */
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'

import FieldControl from '@/components/form-renderer/FieldControl.vue'
import type { FieldDef, FieldState } from '@/types/form'
import { evaluateFormula } from '@/utils/formula'
import { defaultValueOf, formatValue } from '@/utils/formValue'

const props = defineProps<{
  field: FieldDef
  modelValue: unknown
  editable: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [unknown] }>()

const columns = computed(() => props.field.columns ?? [])

const rows = computed<Array<Record<string, unknown>>>(() =>
  Array.isArray(props.modelValue) ? (props.modelValue as Array<Record<string, unknown>>) : [],
)

/** 行内可见列（子表整体可见性由父级决定；行内不做独立三态） */
const visibleColumns = computed(() => columns.value)

const maxRows = computed(() => props.field.validators?.max_rows ?? undefined)
const reachLimit = computed(() => maxRows.value != null && rows.value.length >= maxRows.value)

function emitRows(next: Array<Record<string, unknown>>): void {
  emit('update:modelValue', next)
}

function addRow(): void {
  const row: Record<string, unknown> = {}
  for (const col of columns.value) {
    const def = defaultValueOf(col)
    if (def !== undefined) row[col.key] = def
  }
  recompute(row)
  emitRows([...rows.value, row])
}

function removeRow(index: number): void {
  emitRows(rows.value.filter((_, i) => i !== index))
}

/**
 * 行内公式重算。
 *
 * 「子表合计」类公式在行内没有意义（行内没有子表），跳过即可 ——
 * 服务端也是这么处理的，前端保持一致避免误导。
 */
function recompute(row: Record<string, unknown>): void {
  for (const col of columns.value) {
    if (!col.formula || col.formula.type === 'subtable_sum') continue
    row[col.key] = evaluateFormula(col.formula, row)
  }
}

function onCellChange(row: Record<string, unknown>, colKey: string, value: unknown): void {
  row[colKey] = value
  recompute(row)
  // 子表是整体替换语义：改一行也要把整个数组发出去，父级的值才会更新
  emitRows([...rows.value])
}

function cellState(col: FieldDef): FieldState {
  return { visible: true, editable: props.editable && !col.formula, required: false }
}

function readonlyCell(col: FieldDef, row: Record<string, unknown>): string {
  if (col.formula) return formatValue(col, evaluateFormula(col.formula, row))
  return formatValue(col, row[col.key])
}
</script>

<template>
  <div class="subtable-control">
    <table v-if="!editable" class="subtable readonly">
      <thead>
        <tr>
          <th class="idx">#</th>
          <th v-for="col in visibleColumns" :key="col.key">{{ col.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td class="idx">{{ index + 1 }}</td>
          <td v-for="col in visibleColumns" :key="col.key">{{ readonlyCell(col, row) }}</td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="visibleColumns.length + 1" class="empty">无明细</td>
        </tr>
      </tbody>
    </table>

    <template v-else>
      <div v-for="(row, index) in rows" :key="index" class="subtable-row">
        <div class="row-index">{{ index + 1 }}</div>
        <div class="row-fields">
          <div v-for="col in visibleColumns" :key="col.key" class="row-field">
            <label class="row-label">
              {{ col.label }}
              <span v-if="col.required && !col.formula" class="required">*</span>
            </label>
            <FieldControl
              :field="col"
              :model-value="row[col.key]"
              :state="cellState(col)"
              mode="edit"
              compact
              :values="row"
              @update:model-value="(v) => onCellChange(row, col.key, v)"
            />
          </div>
        </div>
        <a-button type="text" danger size="small" title="删除本行" @click="removeRow(index)">
          <template #icon><DeleteOutlined /></template>
        </a-button>
      </div>

      <a-button type="dashed" block :disabled="reachLimit" @click="addRow">
        <template #icon><PlusOutlined /></template>
        添加一行
      </a-button>
      <div v-if="maxRows" class="text-muted hint">最多 {{ maxRows }} 行</div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.subtable {
  width: 100%;
  border-collapse: collapse;

  th,
  td {
    border: 1px solid #f0f0f0;
    padding: 6px 10px;
    text-align: left;
    font-size: 13px;
  }

  th {
    background: #fafafa;
    font-weight: 500;
  }

  .idx {
    width: 44px;
    color: rgba(0, 0, 0, 0.45);
  }

  .empty {
    text-align: center;
    color: rgba(0, 0, 0, 0.45);
  }
}

.subtable-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px;
  margin-bottom: 8px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}

.row-index {
  flex: 0 0 24px;
  height: 24px;
  line-height: 24px;
  text-align: center;
  border-radius: 12px;
  background: #e6f4ff;
  color: #1677ff;
  font-size: 12px;
}

.row-fields {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
}

.row-field {
  flex: 1 1 160px;
  min-width: 140px;
}

.row-label {
  display: block;
  margin-bottom: 2px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.65);
}

.required {
  color: #ff4d4f;
}

.hint {
  margin-top: 6px;
  font-size: 12px;
}
</style>

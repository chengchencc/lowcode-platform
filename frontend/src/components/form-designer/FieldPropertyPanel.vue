<script setup lang="ts">
/**
 * 字段属性面板（PRD F1.2 / F1.6 / F1.7）。
 *
 * 按控件类型动态显示该类型**用得上的**配置项 —— 给文本字段看「行数上限」
 * 或给下拉看「最小值」都是噪声。校验规则、选项、公式都按类型裁剪。
 */
import { computed } from 'vue'

import type { FieldDef, FieldType, FormSchema } from '@/types/form'
import {
  FIELD_TYPE_LABELS,
  OPTION_FIELD_TYPES,
  SUBTABLE_COLUMN_TYPES,
  isDisplayField,
} from '@/types/form'
import { FORMULA_FUNCTIONS } from '@/utils/formula'
import { normalizeField } from '@/utils/formSchemaEdit'

const props = defineProps<{
  field: FieldDef
  schema: FormSchema
  /** 该字段所属子表的 key（若字段是子表列） */
  parentSubtableKey?: string | null
  /** 是否是子表的列（列的类型选项受限） */
  isColumn?: boolean
}>()

const emit = defineEmits<{ change: [field: FieldDef] }>()

const field = computed(() => props.field)

// --------------------------------------------------------------------------- 可用控件类型

const typeOptions = computed(() => {
  const allowed = props.isColumn ? SUBTABLE_COLUMN_TYPES : (Object.keys(FIELD_TYPE_LABELS) as FieldType[])
  return allowed.map((t) => ({ value: t, label: FIELD_TYPE_LABELS[t] }))
})

function notify(): void {
  emit('change', field.value)
}

/**
 * 切换控件类型时必须补齐该类型需要的子结构 ——
 * 否则切到「公式」后属性面板读 `field.formula.type` 会因 null 直接抛错。
 */
function onTypeChange(): void {
  normalizeField(field.value)
  // 标题字段只能是顶层文本控件；切成别的类型时顺手清掉引用
  if (
    props.schema.title_field === field.value.key
    && field.value.type !== 'text'
    && field.value.type !== 'textarea'
  ) {
    props.schema.title_field = null
  }
  notify()
}

// --------------------------------------------------------------------------- 能力判断

const TEXT_TYPES: FieldType[] = ['text', 'textarea']
const NUMBER_TYPES: FieldType[] = ['number', 'formula']
const DATE_TYPES: FieldType[] = ['date', 'datetime']
const FILE_TYPES: FieldType[] = ['attachment', 'image']
const SUBTABLE_LIKE: FieldType[] = ['subtable']

const isText = computed(() => TEXT_TYPES.includes(field.value.type))
const isNumber = computed(() => NUMBER_TYPES.includes(field.value.type))
const isDate = computed(() => DATE_TYPES.includes(field.value.type))
const isFile = computed(() => FILE_TYPES.includes(field.value.type))
const isSubtable = computed(() => SUBTABLE_LIKE.includes(field.value.type))
const needsOptions = computed(() => OPTION_FIELD_TYPES.includes(field.value.type))
const isFormula = computed(() => field.value.type === 'formula')
const isCascader = computed(() => field.value.type === 'cascader')
const isDisplay = computed(() => isDisplayField(field.value))

/** 发起时自动填充并锁定：顶层人员/部门/日期时间控件支持 */
const autoFillOptions = computed(() => {
  if (props.isColumn) return []
  if (['user', 'user_multi'].includes(field.value.type)) {
    return [{ value: 'initiator', label: '当前发起人' }]
  }
  if (['dept', 'dept_multi'].includes(field.value.type)) {
    return [{ value: 'initiator_dept', label: '发起人所在部门' }]
  }
  if (field.value.type === 'datetime') {
    return [{ value: 'start_time', label: '流程发起时间' }]
  }
  return []
})

/** 发起时带入、但允许发起人修改的默认值 */
const defaultSourceOptions = computed(() => {
  if (props.isColumn) return []
  if (['user', 'user_multi'].includes(field.value.type)) {
    return [{ value: 'initiator', label: '当前发起人' }]
  }
  if (['dept', 'dept_multi'].includes(field.value.type)) {
    return [{ value: 'initiator_dept', label: '发起人所在部门' }]
  }
  return []
})

function onAutoFillChange(value: unknown): void {
  if (value) field.value.default_source = null
  notify()
}

function onDefaultSourceChange(value: unknown): void {
  if (value) field.value.auto_fill = null
  notify()
}

/** 自动编号只适用于顶层单行文本 */
const canAutoNumber = computed(() => !props.isColumn && field.value.type === 'text')

function onAutoNumberToggle(event: unknown): void {
  if (event) {
    field.value.auto_number = { prefix: 'NO', seq_length: 4 }
    field.value.default_value = null
  } else {
    field.value.auto_number = null
  }
  notify()
}

const spanOptions = [
  { value: 24, label: '整行' },
  { value: 12, label: '1/2 行' },
  { value: 8, label: '1/3 行' },
  { value: 6, label: '1/4 行' },
]

const hasValidators = computed(
  () => isText.value || isNumber.value || isDate.value || isFile.value || isSubtable.value,
)

// --------------------------------------------------------------------------- 可用字段引用

/** 公式可引用的字段：同层的其他字段（子表列只能引用本子表的列）。 */
const referenceOptions = computed(() => {
  if (props.isColumn && props.parentSubtableKey) {
    const sub = props.schema.sections
      .flatMap((s) => s.fields)
      .find((f) => f.key === props.parentSubtableKey)
    return (sub?.columns ?? [])
      .filter((c) => c.key !== field.value.key && c.type !== 'formula')
      .map((c) => ({ value: c.key, label: `${c.label}（${c.key}）` }))
  }
  const out: Array<{ value: string; label: string }> = []
  for (const section of props.schema.sections) {
    for (const f of section.fields) {
      if (f.key === field.value.key || isDisplayField(f)) continue
      out.push({ value: f.key, label: `${f.label}（${f.key}）` })
    }
  }
  return out
})

/** 子表合计可选的子表 */
const subtableOptions = computed(() =>
  props.schema.sections
    .flatMap((s) => s.fields)
    .filter((f) => f.type === 'subtable' && !props.isColumn)
    .map((f) => ({ value: f.key, label: `${f.label}（${f.key}）` })),
)

const subtableColumnOptions = computed(() => {
  const sub = props.schema.sections
    .flatMap((s) => s.fields)
    .find((f) => f.key === field.value.formula?.subtable_key)
  return (sub?.columns ?? [])
    .filter((c) => c.type === 'number' || c.type === 'formula')
    .map((c) => ({ value: c.key, label: `${c.label}（${c.key}）` }))
})

const dateFieldOptions = computed(() =>
  props.schema.sections
    .flatMap((s) => s.fields)
    .filter((f) => f.type === 'date' || f.type === 'datetime')
    .map((f) => ({ value: f.key, label: `${f.label}（${f.key}）` })),
)

const parentFieldOptions = computed(() =>
  props.schema.sections
    .flatMap((s) => s.fields)
    .filter(
      (f) =>
        f.key !== field.value.key
        && !isDisplayField(f)
        && ['select', 'radio', 'text'].includes(f.type),
    )
    .map((f) => ({ value: f.key, label: `${f.label}（${f.key}）` })),
)

const formulaFunctions = computed(() => [...FORMULA_FUNCTIONS].join('、'))

// --------------------------------------------------------------------------- 选项编辑

function addOption(): void {
  if (!field.value.options) field.value.options = []
  field.value.options.push({ label: `选项 ${field.value.options.length + 1}`, value: `opt_${field.value.options.length + 1}` })
  notify()
}

function removeOption(index: number): void {
  field.value.options?.splice(index, 1)
  notify()
}

// --------------------------------------------------------------------------- 子表列

function addColumn(): void {
  if (!field.value.columns) field.value.columns = []
  const n = field.value.columns.length + 1
  field.value.columns.push({
    key: `col_${n}`,
    label: `列 ${n}`,
    type: 'text',
    sort: n,
  })
  notify()
}

function removeColumn(index: number): void {
  field.value.columns?.splice(index, 1)
  notify()
}

// --------------------------------------------------------------------------- 默认值

/** 开关/复选等类型不适合用文本框设默认值，给对应的控件 */
const defaultControl = computed(() => {
  if (field.value.type === 'switch') return 'switch'
  if (field.value.type === 'number') return 'number'
  if (needsOptions.value) return 'select'
  if (field.value.type === 'checkbox') return 'checkbox'
  return 'text'
})
</script>

<template>
  <a-form layout="vertical" class="property-panel" size="small">
    <a-tabs>
      <!-- ------------------------------------------------ 基本 -->
      <a-tab-pane key="basic" tab="基本">
        <a-form-item label="控件类型">
          <a-select
            v-model:value="field.type"
            :options="typeOptions"
            @change="onTypeChange"
          />
        </a-form-item>

        <a-form-item label="字段标签" required>
          <a-input
            v-model:value="field.label"
            placeholder="展示给填写人的名称"
            @change="notify"
          />
        </a-form-item>

        <a-form-item label="字段标识" help="实例数据以此作为键；创建后不建议修改（公式、权限矩阵都会引用它）">
          <a-input v-model:value="field.key" class="text-mono" @change="notify" />
        </a-form-item>

        <a-form-item v-if="!isColumn" label="字段宽度" help="24 栅格制；留空则按分区列数自动分配">
          <a-select
            v-model:value="field.span"
            :options="spanOptions"
            allow-clear
            placeholder="自动"
            @change="notify"
          />
        </a-form-item>

        <!-- 展示型控件：只配置展示内容 -->
        <template v-if="isDisplay">
          <a-form-item v-if="field.type === 'heading'" label="标题级别">
            <a-select
              v-model:value="field.display!.level"
              :options="[
                { value: 1, label: '一级标题' },
                { value: 2, label: '二级标题' },
                { value: 3, label: '三级标题' },
              ]"
              @change="notify"
            />
          </a-form-item>

          <a-form-item
            v-if="['heading', 'paragraph', 'divider'].includes(field.type)"
            label="展示文字"
            :help="field.type === 'divider' ? '可留空，只显示一条分割线' : undefined"
          >
            <a-input v-model:value="field.display!.text" @change="notify" />
          </a-form-item>

          <template v-if="field.type === 'image_view'">
            <a-form-item label="图片地址" help="支持 http(s) 链接或站内 / 开头的路径">
              <a-input v-model:value="field.display!.url" @change="notify" />
            </a-form-item>
            <a-form-item label="替代文字">
              <a-input v-model:value="field.display!.alt" @change="notify" />
            </a-form-item>
          </template>

          <a-form-item
            v-if="field.type === 'rich_text'"
            label="Markdown 内容"
            help="支持标题、列表、粗体/斜体、链接、行内代码；不允许 HTML 标签"
          >
            <a-textarea v-model:value="field.display!.markdown" :rows="6" @change="notify" />
          </a-form-item>
        </template>

        <!-- 数据字段：填写与校验配置 -->
        <template v-else>
          <a-form-item label="占位提示">
            <a-input v-model:value="field.placeholder" placeholder="输入框里的灰字提示" @change="notify" />
          </a-form-item>

          <a-form-item label="帮助说明" help="显示在控件下方的小字">
            <a-input v-model:value="field.help" @change="notify" />
          </a-form-item>

          <a-form-item v-if="!isFormula" label="必填">
            <a-switch v-model:checked="field.required" @change="notify" />
          </a-form-item>

          <a-form-item v-if="canAutoNumber" label="自动生成编号">
            <a-switch :checked="!!field.auto_number" @change="onAutoNumberToggle" />
            <template #extra>
              <span class="text-muted">
                标识位 + 年月日 + 当日流水号，例如 REQ202611110001；发起时由服务端生成并锁定
              </span>
            </template>
          </a-form-item>

          <template v-if="field.auto_number">
            <a-form-item label="编号标识位" help="如 REQ / BX / QJ，仅字母数字、下划线、短横线">
              <a-input
                v-model:value="field.auto_number.prefix"
                placeholder="REQ"
                class="text-mono"
                @change="notify"
              />
            </a-form-item>
            <a-form-item label="流水号位数" help="左侧补零，默认 4 位">
              <a-input-number
                v-model:value="field.auto_number.seq_length"
                :min="1"
                :max="8"
                style="width: 100%"
                @change="notify"
              />
            </a-form-item>
          </template>

          <a-form-item v-if="autoFillOptions.length" label="发起时自动填充">
            <a-select
              v-model:value="field.auto_fill"
              :options="autoFillOptions"
              allow-clear
              placeholder="不自动填充"
              @change="onAutoFillChange"
            />
            <template #extra>
              <span class="text-muted">
                发起时由系统带入并锁定；后续节点可按字段权限继续编辑
              </span>
            </template>
          </a-form-item>

          <a-form-item
            v-if="defaultSourceOptions.length && !field.auto_fill"
            label="发起时默认值"
          >
            <a-select
              v-model:value="field.default_source"
              :options="defaultSourceOptions"
              allow-clear
              placeholder="不设置默认值"
              @change="onDefaultSourceChange"
            />
            <template #extra>
              <span class="text-muted">
                发起时带入、但发起人仍可修改（与「自动填充并锁定」二选一）
              </span>
            </template>
          </a-form-item>

          <a-form-item label="发起阶段可见">
            <a-switch v-model:checked="field.visible_at_start" @change="notify" />
            <template #extra>
              <span class="text-muted">
                关闭后该字段在发起页隐藏，由流程节点显式打开 —— 这就是「财务补充字段」的做法
              </span>
            </template>
          </a-form-item>

          <a-form-item
            v-if="!field.auto_fill && !field.default_source && !field.auto_number"
            label="默认值"
          >
            <a-switch
              v-if="defaultControl === 'switch'"
              v-model:checked="field.default_value as boolean"
              @change="notify"
            />
            <a-input-number
              v-else-if="defaultControl === 'number'"
              v-model:value="field.default_value as number"
              style="width: 100%"
              @change="notify"
            />
            <a-select
              v-else-if="defaultControl === 'select'"
              v-model:value="field.default_value"
              :options="(field.options ?? []).map((o) => ({ value: o.value, label: o.label }))"
              allow-clear
              @change="notify"
            />
            <a-checkbox-group
              v-else-if="defaultControl === 'checkbox'"
              v-model:value="field.default_value as Array<string | number>"
              :options="(field.options ?? []).map((o) => ({ value: o.value, label: o.label }))"
              @change="notify"
            />
            <a-input v-else v-model:value="field.default_value as string" @change="notify" />
          </a-form-item>
        </template>
      </a-tab-pane>

      <!-- ------------------------------------------------ 选项 -->
      <a-tab-pane v-if="needsOptions" key="options" tab="选项">
        <div v-for="(opt, index) in field.options ?? []" :key="index" class="option-row">
          <a-input
            v-model:value="opt.label"
            placeholder="显示文本"
            @change="notify"
          />
          <a-input
            v-model:value="opt.value as string"
            placeholder="值"
            class="text-mono"
            @change="notify"
          />
          <a-button type="text" danger size="small" @click="removeOption(index)">删除</a-button>
        </div>
        <a-button type="dashed" block size="small" @click="addOption">添加选项</a-button>
        <p class="text-muted tip">选项值在同一字段内必须唯一；混用文字与数字会导致选中态失效</p>
      </a-tab-pane>

      <!-- ------------------------------------------------ 校验 -->
      <a-tab-pane v-if="hasValidators" key="validators" tab="校验">
        <template v-if="isText">
          <a-form-item label="最小长度">
            <a-input-number
              v-model:value="field.validators!.min_length as number"
              :min="0"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="最大长度">
            <a-input-number
              v-model:value="field.validators!.max_length as number"
              :min="1"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="正则表达式" help="需匹配整个值；如手机号 ^1[3-9]\d{9}$">
            <a-input
              v-model:value="field.validators!.regex as string"
              class="text-mono"
              @change="notify"
            />
          </a-form-item>
        </template>

        <template v-if="isNumber">
          <a-form-item label="最小值">
            <a-input-number
              v-model:value="field.validators!.min as number"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="最大值">
            <a-input-number
              v-model:value="field.validators!.max as number"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
          <a-form-item v-if="!isFormula" label="小数位">
            <a-input-number
              v-model:value="field.validators!.precision as number"
              :min="0"
              :max="6"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
        </template>

        <template v-if="isFile">
          <a-form-item label="最多文件数">
            <a-input-number
              v-model:value="field.validators!.max_file_count as number"
              :min="1"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="单文件上限 (MB)">
            <a-input-number
              v-model:value="field.validators!.max_file_size_mb as number"
              :min="1"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
        </template>

        <template v-if="isSubtable">
          <a-form-item label="最少行数">
            <a-input-number
              v-model:value="field.validators!.min_rows as number"
              :min="0"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="最多行数">
            <a-input-number
              v-model:value="field.validators!.max_rows as number"
              :min="1"
              style="width: 100%"
              @change="notify"
            />
          </a-form-item>
        </template>
      </a-tab-pane>

      <!-- ------------------------------------------------ 子表列 -->
      <a-tab-pane v-if="isSubtable" key="columns" tab="行内列">
        <div v-for="(col, index) in field.columns ?? []" :key="index" class="column-row">
          <a-input v-model:value="col.label" placeholder="列名" @change="notify" />
          <a-input v-model:value="col.key" placeholder="标识" class="text-mono" @change="notify" />
          <a-button type="text" danger size="small" @click="removeColumn(index)">删除</a-button>
        </div>
        <a-button type="dashed" block size="small" @click="addColumn">添加列</a-button>
        <p class="text-muted tip">
          添加后可在左侧清单里选中某一列继续配置它的类型、校验与公式
        </p>
      </a-tab-pane>

      <!-- ------------------------------------------------ 公式 -->
      <a-tab-pane v-if="isFormula" key="formula" tab="公式">
        <a-alert
          type="info"
          show-icon
          class="formula-tip"
          :message="`支持四则运算、子表合计、日期差、文本拼接；可用函数：${formulaFunctions}`"
          description="公式结果由服务端在提交时重算，前端只做即时显示"
        />

        <a-form-item label="公式类型">
          <a-select
            v-model:value="field.formula!.type"
            :options="[
              { value: 'arithmetic', label: '数字四则' },
              { value: 'subtable_sum', label: '子表合计' },
              { value: 'date_diff', label: '日期差（天）' },
              { value: 'concat', label: '文本拼接' },
            ]"
            @change="notify"
          />
        </a-form-item>

        <template v-if="field.formula!.type === 'arithmetic' || field.formula!.type === 'concat'">
          <a-form-item label="表达式" help="用字段标识参与运算，如 qty * price 或 ROUND(a + b, 2)">
            <a-input
              v-model:value="field.formula!.expression as string"
              class="text-mono"
              placeholder="qty * price"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="可引用字段">
            <div class="ref-list">
              <a-tag
                v-for="ref in referenceOptions"
                :key="ref.value"
                class="ref-tag"
                @click="
                  () => {
                    field.formula!.expression = `${field.formula!.expression ?? ''}${ref.value}`
                    notify()
                  }
                "
              >
                {{ ref.value }}
              </a-tag>
              <span v-if="!referenceOptions.length" class="text-muted">同层还没有其他字段</span>
            </div>
          </a-form-item>
        </template>

        <template v-else-if="field.formula!.type === 'subtable_sum'">
          <a-form-item label="子表">
            <a-select
              v-model:value="field.formula!.subtable_key"
              :options="subtableOptions"
              placeholder="选择要合计的子表"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="合计列">
            <a-select
              v-model:value="field.formula!.column_key"
              :options="subtableColumnOptions"
              placeholder="选择要合计的列"
              @change="notify"
            />
          </a-form-item>
        </template>

        <template v-else-if="field.formula!.type === 'date_diff'">
          <a-form-item label="起始日期字段">
            <a-select
              v-model:value="field.formula!.start_field"
              :options="dateFieldOptions"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="结束日期字段">
            <a-select
              v-model:value="field.formula!.end_field"
              :options="dateFieldOptions"
              @change="notify"
            />
          </a-form-item>
        </template>
      </a-tab-pane>

      <!-- ------------------------------------------------ 级联 -->
      <a-tab-pane v-if="isCascader" key="cascader" tab="级联">
        <a-form-item label="父字段" help="本字段的候选项由该字段的当前值决定">
          <a-select
            v-model:value="field.cascader!.parent_field"
            :options="parentFieldOptions"
            @change="notify"
          />
        </a-form-item>
        <a-alert
          type="warning"
          show-icon
          message="M2 阶段级联选项需在 JSON 中配置"
          description="图形化的「父值 → 子选项」编辑器排在后续里程碑"
        />
      </a-tab-pane>
    </a-tabs>
  </a-form>
</template>

<style scoped lang="scss">
.property-panel {
  :deep(.ant-tabs-nav) {
    margin-bottom: 12px;
  }
}

.option-row,
.column-row {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
  align-items: center;

  :deep(.ant-input) {
    flex: 1;
  }
}

.tip {
  margin: 8px 0 0;
  font-size: 12px;
}

.formula-tip {
  margin-bottom: 12px;
}

.ref-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ref-tag {
  cursor: pointer;
  margin: 0;

  &:hover {
    color: #1677ff;
    border-color: #1677ff;
  }
}
</style>

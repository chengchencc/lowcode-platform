<script setup lang="ts">
/**
 * 表单配置器（PRD F1.1–F1.7）。
 *
 * 布局：左侧分区/字段清单 + 右侧属性面板 + 抽屉实时预览。
 * 排序用上下移动按钮而非拖拽 —— 拖拽要引入额外依赖（vuedraggable），
 * 而上下移动 + 跨分区移动已经覆盖了功能需求，见 docs/TECH-DESIGN.md 的说明。
 *
 * 保存策略：改动后 1.5s 防抖自动保存。**保存不做语义校验**（后端刻意如此），
 * 所以「单选还没配选项」也能存下来，不会打断配置过程；发布时才拦。
 */
import {
  ArrowDownOutlined,
  ArrowLeftOutlined,
  ArrowUpOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'
import { Button, Card, Drawer, Empty, Space, Tag, Tooltip } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { formApi } from '@/api/modules/form'
import FieldPropertyPanel from '@/components/form-designer/FieldPropertyPanel.vue'
import { FormRenderer } from '@/components/form-renderer'
import type {
  FieldDef,
  FormSchema,
  FormTemplate,
  FormValidateResult,
  FormVersion,
  SectionDef,
} from '@/types/form'
import { FIELD_TYPE_GROUPS, FIELD_TYPE_LABELS, SECTION_STAGE_LABELS } from '@/types/form'
import { buildInitialValues } from '@/utils/formValue'
import { makeColumn, makeField, makeSection, moveInArray, normalizeField, resequence, stripFormulaRefs } from '@/utils/formSchemaEdit'
import { feedback } from '@/utils/feedback'

const route = useRoute()
const router = useRouter()

const templateId = computed(() => Number(route.params.id))

const template = ref<FormTemplate | null>(null)
const version = ref<FormVersion | null>(null)
// 初始就要有 layout：首次渲染发生在 onMounted(load) 之前，
// 而左侧“整体布局”会直接读 schema.layout；缺了它会整页渲染失败变白屏。
const schema = ref<FormSchema>({
  sections: [],
  layout: { label_position: 'top', columns: 2 },
})
const columnOptions = [1, 2, 3, 4].map((n) => ({ value: n, label: `${n} 列` }))
const loading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const lastSavedAt = ref<Date | null>(null)
const dirty = ref(false)

// --------------------------------------------------------------------------- 选中项

/** 当前选中的字段。columnKey 非空表示选中的是子表里的某一列。 */
const selected = ref<{ sectionKey: string; fieldKey: string; columnKey?: string } | null>(null)

const selectedSection = computed<SectionDef | null>(
  () => schema.value.sections.find((s) => s.key === selected.value?.sectionKey) ?? null,
)

const selectedField = computed<FieldDef | null>(() => {
  const sel = selected.value
  if (!sel) return null
  const section = selectedSection.value
  if (!section) return null
  const field = section.fields.find((f) => f.key === sel.fieldKey)
  if (!field) return null
  if (sel.columnKey) {
    return (field.columns ?? []).find((c) => c.key === sel.columnKey) ?? null
  }
  return field
})

/** 选中字段所在的子表（若它是列） */
const selectedParentSubtable = computed<FieldDef | null>(() => {
  if (!selected.value?.columnKey) return null
  return selectedSection.value?.fields.find((f) => f.key === selected.value!.fieldKey) ?? null
})

// --------------------------------------------------------------------------- 加载

async function load(): Promise<void> {
  loading.value = true
  try {
    template.value = await formApi.getTemplate(templateId.value)
    // 有草稿就编辑草稿，否则从当前发布版本 fork 一个草稿
    let target: FormVersion
    if (template.value.draft_version_id) {
      target = await formApi.getVersion(template.value.draft_version_id)
    } else {
      target = await formApi.createVersion(templateId.value, template.value.current_version_id)
    }
    version.value = target
    schema.value = normalizeSchema(target.schema_data)
    if (schema.value.sections.length) {
      selected.value = {
        sectionKey: schema.value.sections[0].key,
        fieldKey: schema.value.sections[0].fields[0]?.key ?? '',
      }
      if (!selectedField.value) selected.value = null
    }
  } finally {
    loading.value = false
  }
}

/** 补齐服务端可能省略的可选结构，避免属性面板读到 null。 */
function normalizeSchema(input: FormSchema): FormSchema {
  const next: FormSchema = {
    model_version: input.model_version ?? 1,
    layout: input.layout ?? { label_position: 'top', columns: 2 },
    sections: (input.sections ?? []).map((section) => ({
      ...section,
      stage: section.stage ?? 'apply',
      // antd Select 不接受 null：分区列数留空统一用 undefined
      columns: section.columns ?? undefined,
      fields: (section.fields ?? []).map((f) => {
        normalizeField(f)
        for (const col of f.columns ?? []) normalizeField(col)
        return f
      }),
    })),
  }
  return next
}

onMounted(load)

// --------------------------------------------------------------------------- 自动保存

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  dirty.value = true
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void save(), 1500)
}

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})

async function save(): Promise<boolean> {
  if (!version.value || !dirty.value) return true
  saving.value = true
  try {
    const updated = await formApi.saveVersion(version.value.id, schema.value)
    version.value = updated
    lastSavedAt.value = new Date()
    dirty.value = false
    return true
  } catch (error) {
    // 形状错误（不是语义错误）才会走到这里；语义问题留给发布拦
    if (error instanceof ApiError) feedback.error(error.message)
    return false
  } finally {
    saving.value = false
  }
}

/** 属性面板的任何改动都会回调这里 */
function onFieldChange(): void {
  resequence(selectedSection.value?.fields ?? [])
  scheduleSave()
}

// --------------------------------------------------------------------------- 分区操作

function addSection(): void {
  const section = makeSection(schema.value)
  schema.value.sections.push(section)
  resequence(schema.value.sections)
  selected.value = null
  scheduleSave()
}

function removeSection(section: SectionDef): void {
  const ok = window.confirm(
    `删除分区「${section.title}」及其中的 ${section.fields.length} 个字段？`,
  )
  if (!ok) return
  schema.value.sections = schema.value.sections.filter((s) => s.key !== section.key)
  if (selected.value?.sectionKey === section.key) selected.value = null
  scheduleSave()
}

function moveSection(index: number, delta: number): void {
  if (moveInArray(schema.value.sections, index, delta)) {
    resequence(schema.value.sections)
    scheduleSave()
  }
}

// --------------------------------------------------------------------------- 字段操作

function addField(section: SectionDef, type: FieldDef['type']): void {
  const field = makeField(schema.value, type)
  section.fields.push(field)
  resequence(section.fields)
  selected.value = { sectionKey: section.key, fieldKey: field.key }
  scheduleSave()
}

function removeField(section: SectionDef, field: FieldDef): void {
  section.fields = section.fields.filter((f) => f.key !== field.key)
  // 顺手清掉引用它的公式，避免留下必然报错的配置
  const cleaned = stripFormulaRefs(schema.value, field.key)
  if (cleaned.length) {
    feedback.warning(`已同时清空引用它的公式：${cleaned.join('、')}`)
  }
  if (selected.value?.fieldKey === field.key) selected.value = null
  scheduleSave()
}

function moveField(section: SectionDef, index: number, delta: number): void {
  if (moveInArray(section.fields, index, delta)) {
    resequence(section.fields)
    scheduleSave()
  }
}

/** 把字段移到相邻分区（PRD F1.2「移动分区」） */
function moveToAdjacentSection(section: SectionDef, field: FieldDef, delta: number): void {
  const index = schema.value.sections.indexOf(section)
  const target = schema.value.sections[index + delta]
  if (!target) return
  section.fields = section.fields.filter((f) => f.key !== field.key)
  target.fields.push(field)
  resequence(section.fields)
  resequence(target.fields)
  selected.value = { sectionKey: target.key, fieldKey: field.key }
  scheduleSave()
}

function addColumn(subtable: FieldDef): void {
  subtable.columns ??= []
  const col = makeColumn(subtable)
  subtable.columns.push(col)
  if (selectedSection.value) {
    selected.value = {
      sectionKey: selectedSection.value.key,
      fieldKey: subtable.key,
      columnKey: col.key,
    }
  }
  scheduleSave()
}

function removeColumn(subtable: FieldDef, col: FieldDef): void {
  subtable.columns = (subtable.columns ?? []).filter((c) => c.key !== col.key)
  if (selected.value?.columnKey === col.key) {
    selected.value = { sectionKey: selected.value.sectionKey, fieldKey: subtable.key }
  }
  scheduleSave()
}

// --------------------------------------------------------------------------- 校验与发布

const validateResult = ref<FormValidateResult | null>(null)
const validateOpen = ref(false)

async function runValidate(): Promise<void> {
  if (!(await save())) return
  validateResult.value = await formApi.validateVersion(version.value!.id)
  validateOpen.value = true
}

async function publish(): Promise<void> {
  if (!(await save())) return

  const result = await formApi.validateVersion(version.value!.id)
  if (!result.valid) {
    validateResult.value = result
    validateOpen.value = true
    feedback.error('还有错误未修复，无法发布')
    return
  }

  const ok = await feedback.confirm({
    title: `发布 v${version.value!.version_no}？`,
    content: '发布后该版本冻结不可修改；后续改动需新建版本。上一个发布版本会归档。',
  })
  if (!ok) return

  publishing.value = true
  try {
    await formApi.publishVersion(version.value!.id)
    feedback.success('已发布')
    await load()
  } catch (error) {
    if (error instanceof ApiError) feedback.error(error.message)
  } finally {
    publishing.value = false
  }
}

// --------------------------------------------------------------------------- 预览

const previewOpen = ref(false)
const previewValues = ref<Record<string, unknown>>({})
const previewMode = ref<'edit' | 'readonly'>('edit')
const serverComputed = ref<Record<string, unknown>>({})

function openPreview(): void {
  previewValues.value = buildInitialValues(schema.value)
  serverComputed.value = {}
  previewOpen.value = true
}

/** 用服务端重算一遍，验证前后端公式结果一致（决策 D4） */
async function refreshServerComputed(): Promise<void> {
  if (!version.value) return
  try {
    const result = await formApi.previewVersion(version.value.id, previewValues.value)
    serverComputed.value = result.sample_data as Record<string, unknown>
  } catch {
    // 保存过就能预览；失败静默，前端本地结果仍然可用
  }
}

watch(previewOpen, (open) => {
  if (open) void refreshServerComputed()
})

const versionLabel = computed(() => {
  if (!version.value) return ''
  const status = version.value.status
  const text = status === 'DRAFT' ? '草稿' : status === 'PUBLISHED' ? '已发布' : '已归档'
  return `v${version.value.version_no} · ${text}`
})

const readonly = computed(() => version.value?.status !== 'DRAFT')
</script>

<template>
  <div class="page-container designer">
    <Card :bordered="false" class="designer-header" :body-style="{ padding: '12px 16px' }">
      <div class="header-row">
        <Space>
          <Button type="text" @click="router.push({ name: 'form-templates' })">
            <template #icon><ArrowLeftOutlined /></template>
          </Button>
          <span class="title">{{ template?.name }}</span>
          <Tag :color="version?.status === 'PUBLISHED' ? 'green' : 'orange'">
            {{ versionLabel }}
          </Tag>
          <Tag v-if="readonly" color="red">已冻结，不可编辑</Tag>
        </Space>

        <Space>
          <span class="text-muted save-hint">
            <template v-if="saving">保存中…</template>
            <template v-else-if="dirty">有未保存的改动</template>
            <template v-else-if="lastSavedAt">已保存</template>
          </span>
          <Button :disabled="readonly" :loading="saving" @click="save">
            <template #icon><SaveOutlined /></template>
            保存
          </Button>
          <Button @click="runValidate">
            <template #icon><CheckCircleOutlined /></template>
            校验
          </Button>
          <Button @click="openPreview">
            <template #icon><EyeOutlined /></template>
            预览
          </Button>
          <!-- 只用 readonly 做禁用：设计器有自动保存，dirty 会很快变回 false，
               用它做条件会让按钮在保存后立刻变灰。publish() 内部会先 save()。 -->
          <Button
            type="primary"
            :disabled="readonly"
            :loading="publishing"
            @click="publish"
          >
            发布
          </Button>
        </Space>
      </div>
    </Card>

    <a-row :gutter="16" class="designer-body">
      <!-- ------------------------------------------------ 左侧清单 -->
      <a-col :xs="24" :md="9" :lg="7">
        <Card :bordered="false" :loading="loading" class="panel">
          <template #title>表单结构</template>
          <template #extra>
            <Button size="small" @click="addSection">
              <template #icon><PlusOutlined /></template>
              分区
            </Button>
          </template>

          <div class="form-layout-settings">
            <div class="layout-title">整体布局</div>
            <a-form layout="inline" size="small">
              <a-form-item label="标签位置">
                <a-select
                  v-model:value="schema.layout!.label_position"
                  :options="[
                    { value: 'top', label: '顶部' },
                    { value: 'left', label: '左侧' },
                  ]"
                  @change="scheduleSave"
                />
              </a-form-item>
              <a-form-item label="默认列数">
                <a-select
                  v-model:value="schema.layout!.columns"
                  :options="columnOptions"
                  @change="scheduleSave"
                />
              </a-form-item>
            </a-form>
          </div>

          <a-empty v-if="!schema.sections.length" description="还没有分区" />

          <div
            v-for="(section, sIndex) in schema.sections"
            :key="section.key"
            class="section-group"
          >
            <div
              class="section-head"
              :class="{ active: selected?.sectionKey === section.key && !selected?.fieldKey }"
              @click="selected = null"
            >
              <span class="section-name">{{ section.title }}</span>
              <Tag class="stage-mini">{{ SECTION_STAGE_LABELS[section.stage ?? 'apply'] }}</Tag>
              <span class="spacer" />
              <Tooltip title="上移">
                <Button type="text" size="small" @click.stop="moveSection(sIndex, -1)">
                  <template #icon><ArrowUpOutlined /></template>
                </Button>
              </Tooltip>
              <Tooltip title="下移">
                <Button type="text" size="small" @click.stop="moveSection(sIndex, 1)">
                  <template #icon><ArrowDownOutlined /></template>
                </Button>
              </Tooltip>
              <Tooltip title="删除分区">
                <Button type="text" size="small" danger @click.stop="removeSection(section)">
                  <template #icon><DeleteOutlined /></template>
                </Button>
              </Tooltip>
            </div>

            <div class="field-list">
              <div
                v-for="(field, fIndex) in section.fields"
                :key="field.key"
                class="field-item"
                :class="{
                  active:
                    selected?.fieldKey === field.key && !selected?.columnKey,
                }"
                @click="selected = { sectionKey: section.key, fieldKey: field.key }"
              >
                <span class="field-label">{{ field.label }}</span>
                <span class="field-type">{{ FIELD_TYPE_LABELS[field.type] }}</span>
                <span class="spacer" />
                <Tooltip title="上移">
                  <Button type="text" size="small" @click.stop="moveField(section, fIndex, -1)">
                    <template #icon><ArrowUpOutlined /></template>
                  </Button>
                </Tooltip>
                <Tooltip title="下移">
                  <Button type="text" size="small" @click.stop="moveField(section, fIndex, 1)">
                    <template #icon><ArrowDownOutlined /></template>
                  </Button>
                </Tooltip>
                <Tooltip title="移到上一个分区">
                  <Button
                    type="text"
                    size="small"
                    :disabled="sIndex === 0"
                    @click.stop="moveToAdjacentSection(section, field, -1)"
                  >
                    ↑区
                  </Button>
                </Tooltip>
                <Tooltip title="移到下一个分区">
                  <Button
                    type="text"
                    size="small"
                    :disabled="sIndex === schema.sections.length - 1"
                    @click.stop="moveToAdjacentSection(section, field, 1)"
                  >
                    ↓区
                  </Button>
                </Tooltip>
                <Tooltip title="删除字段">
                  <Button
                    type="text"
                    size="small"
                    danger
                    @click.stop="removeField(section, field)"
                  >
                    <template #icon><DeleteOutlined /></template>
                  </Button>
                </Tooltip>
              </div>

              <!-- 子表列 -->
              <template v-for="field in section.fields" :key="`cols-${field.key}`">
                <div v-if="field.type === 'subtable' && field.columns?.length" class="column-list">
                  <div class="column-head">
                    子表「{{ field.label }}」的列
                    <a
                      v-if="selected?.fieldKey === field.key"
                      @click.stop="addColumn(field)"
                    >
                      + 添加列
                    </a>
                  </div>
                  <div
                    v-for="col in field.columns"
                    :key="col.key"
                    class="field-item column-item"
                    :class="{
                      active:
                        selected?.fieldKey === field.key && selected?.columnKey === col.key,
                    }"
                    @click="
                      selected = { sectionKey: section.key, fieldKey: field.key, columnKey: col.key }
                    "
                  >
                    <span class="field-label">{{ col.label }}</span>
                    <span class="field-type">{{ FIELD_TYPE_LABELS[col.type] }}</span>
                    <span class="spacer" />
                    <Button
                      type="text"
                      size="small"
                      danger
                      @click.stop="removeColumn(field, col)"
                    >
                      <template #icon><DeleteOutlined /></template>
                    </Button>
                  </div>
                </div>
              </template>

              <a-dropdown :trigger="['click']" placement="bottomLeft">
                <a-button type="dashed" block size="small" class="add-field-btn">
                  <template #icon><PlusOutlined /></template>
                  添加字段
                </a-button>
                <template #overlay>
                  <a-menu class="field-menu">
                    <template v-for="group in FIELD_TYPE_GROUPS" :key="group.title">
                      <a-menu-item-group :title="group.title">
                        <a-menu-item
                          v-for="t in group.types"
                          :key="t"
                          @click="addField(section, t)"
                        >
                          {{ FIELD_TYPE_LABELS[t] }}
                        </a-menu-item>
                      </a-menu-item-group>
                    </template>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>
          </div>
        </Card>
      </a-col>

      <!-- ------------------------------------------------ 右侧属性 -->
      <a-col :xs="24" :md="15" :lg="17">
        <Card :bordered="false" class="panel">
          <template #title>
            <template v-if="selectedField">
              字段属性：{{ selectedField.label }}
              <Tag v-if="selectedParentSubtable" class="stage-mini">
                子表「{{ selectedParentSubtable.label }}」的列
              </Tag>
            </template>
            <template v-else-if="selectedSection">分区属性：{{ selectedSection.title }}</template>
            <template v-else>字段属性</template>
          </template>

          <!-- 选中字段 -->
          <FieldPropertyPanel
            v-if="selectedField"
            :field="selectedField"
            :schema="schema"
            :is-column="Boolean(selected?.columnKey)"
            :parent-subtable-key="selectedParentSubtable?.key ?? null"
            @change="onFieldChange"
          />

          <!-- 选中分区 -->
          <a-form v-else-if="selectedSection" layout="vertical" size="small" class="section-form">
            <a-form-item label="分区名称">
              <a-input v-model:value="selectedSection.title" @change="scheduleSave" />
            </a-form-item>
            <a-form-item label="分区标识" help="流程的字段权限矩阵按分区批量设置时会引用它">
              <a-input v-model:value="selectedSection.key" class="text-mono" @change="scheduleSave" />
            </a-form-item>
            <a-form-item label="阶段标签">
              <a-select
                v-model:value="selectedSection.stage"
                :options="
                  Object.entries(SECTION_STAGE_LABELS).map(([value, label]) => ({
                    value,
                    label,
                  }))
                "
                @change="scheduleSave"
              />
            </a-form-item>
            <a-form-item label="分区说明">
              <a-textarea v-model:value="selectedSection.description" :rows="2" @change="scheduleSave" />
            </a-form-item>
            <a-form-item label="分区列数" help="留空则跟随表单默认列数">
              <a-select
                v-model:value="selectedSection.columns"
                :options="columnOptions"
                allow-clear
                placeholder="跟随表单"
                @change="scheduleSave"
              />
            </a-form-item>
            <a-form-item label="可折叠">
              <a-switch v-model:checked="selectedSection.collapsible" @change="scheduleSave" />
            </a-form-item>
            <a-alert
              type="info"
              show-icon
              message="阶段标签决定该分区在审批节点上的默认可见性"
              description="申请区在发起时可编辑；补充区的字段默认对所有节点隐藏，由流程的字段权限矩阵逐节点打开。"
            />
          </a-form>

          <Empty v-else description="从左侧选择一个字段或分区开始配置" />
        </Card>
      </a-col>
    </a-row>

    <!-- ------------------------------------------------ 校验结果 -->
    <Drawer
      v-model:open="validateOpen"
      title="结构校验"
      :width="520"
      placement="right"
    >
      <template v-if="validateResult">
        <a-alert
          :type="validateResult.valid ? 'success' : 'error'"
          show-icon
          :message="
            validateResult.valid
              ? '没有阻断性问题，可以发布'
              : `发现 ${validateResult.errors.length} 个错误，无法发布`
          "
          style="margin-bottom: 16px"
        />
        <div v-if="validateResult.errors.length">
          <h4>错误</h4>
          <ul class="issue-list">
            <li v-for="(issue, i) in validateResult.errors" :key="i">
              <span class="issue-code">{{ issue.code }}</span>
              {{ issue.message }}
              <div v-if="issue.path" class="text-muted path">{{ issue.path }}</div>
            </li>
          </ul>
        </div>
        <div v-if="validateResult.warnings.length">
          <h4>提示</h4>
          <ul class="issue-list warn">
            <li v-for="(issue, i) in validateResult.warnings" :key="i">
              <span class="issue-code">{{ issue.code }}</span>
              {{ issue.message }}
              <div v-if="issue.path" class="text-muted path">{{ issue.path }}</div>
            </li>
          </ul>
        </div>
      </template>
    </Drawer>

    <!-- ------------------------------------------------ 预览 -->
    <Drawer v-model:open="previewOpen" title="表单预览" :width="760" placement="right">
      <template #extra>
        <a-radio-group v-model:value="previewMode" size="small" button-style="solid">
          <a-radio-button value="edit">编辑态</a-radio-button>
          <a-radio-button value="readonly">只读态</a-radio-button>
        </a-radio-group>
      </template>

      <FormRenderer
        v-model="previewValues"
        :schema="schema"
        :mode="previewMode"
        empty-text="还没有配置任何字段"
      />

      <a-collapse v-if="Object.keys(serverComputed).length" ghost style="margin-top: 16px">
        <a-collapse-panel key="server" header="服务端重算结果（提交时以它为准）">
          <pre class="computed-json">{{ JSON.stringify(serverComputed, null, 2) }}</pre>
        </a-collapse-panel>
      </a-collapse>
    </Drawer>
  </div>
</template>

<style scoped lang="scss">
.designer-header {
  margin-bottom: 12px;
  border-radius: 8px;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.title {
  font-size: 16px;
  font-weight: 600;
}

.save-hint {
  font-size: 12px;
}

.designer-body {
  align-items: flex-start;
}

.form-layout-settings {
  margin-bottom: 12px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fafafa;
}

.layout-title {
  margin-bottom: 6px;
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.panel {
  border-radius: 8px;
  min-height: 520px;

  :deep(.ant-card-body) {
    padding: 12px;
  }
}

.section-group {
  margin-bottom: 14px;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #f5f7fa;
  cursor: pointer;

  &.active {
    background: #e6f4ff;
  }
}

.section-name {
  font-weight: 600;
  font-size: 13px;
}

.stage-mini {
  font-size: 11px;
  margin: 0;
  transform: scale(0.9);
}

.spacer {
  flex: 1;
}

.field-list {
  padding-left: 8px;
  margin-top: 4px;
}

.field-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;

  &:hover {
    background: #fafafa;
  }

  &.active {
    background: #e6f4ff;
  }
}

.field-label {
  font-weight: 500;
}

.field-type {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.45);
}

.column-list {
  margin: 4px 0 8px 18px;
  padding-left: 8px;
  border-left: 2px solid #e6f4ff;
}

.column-head {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: rgba(0, 0, 0, 0.45);
  padding: 2px 0;
}

.column-item {
  font-size: 12px;
}

.add-field-btn {
  margin-top: 6px;
}

.section-form {
  max-width: 520px;
}

.issue-list {
  padding-left: 18px;
  margin: 8px 0 16px;

  li {
    margin-bottom: 8px;
    font-size: 13px;
  }

  &.warn li {
    color: rgba(0, 0, 0, 0.65);
  }
}

.issue-code {
  display: inline-block;
  padding: 0 5px;
  margin-right: 6px;
  border-radius: 3px;
  background: #fff1f0;
  color: #cf1322;
  font-size: 11px;
  font-family: monospace;
}

.path {
  font-size: 11px;
  font-family: monospace;
}

.computed-json {
  max-height: 240px;
  overflow: auto;
  background: #fafafa;
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
}
</style>

<style>
/* 字段类型菜单可能有 19 项，给个高度上限 */
.field-menu {
  max-height: 420px;
  overflow: auto;
}
</style>

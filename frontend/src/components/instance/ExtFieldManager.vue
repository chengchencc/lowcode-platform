<script setup lang="ts">
/**
 * 机制 C：运行中追加字段（PRD §3.4 / F5.1）。
 *
 * 场景：报销跑到财务那一步才发现要留「合同编号」—— 重做模板已来不及，
 * 于是**只给这一张单**加一个字段。
 *
 * 界面上要讲清楚的四条约束（PRD 明列，服务端同样会拦）：
 * - 只对该实例生效，不进模板
 * - 追加后**不可删除，只能停用** —— 历史快照里还有它的值
 * - 默认只读，只有指定的目标节点可填；追加点之前的节点看不到
 * - 只支持基础控件（不收子表与公式）
 *
 * 「可编辑节点」的候选来自进度条的审批/填写节点 —— 条件与并行容器没有处理人，
 * 不该出现在这个下拉里。
 */
import { PlusOutlined } from '@ant-design/icons-vue'
import { Button } from 'ant-design-vue'
import { computed, ref } from 'vue'

import { instanceApi } from '@/api/modules/instance'
import type { FieldType } from '@/types/form'
import { FIELD_TYPE_LABELS } from '@/types/form'
import type { ExtFieldItem, ExtFieldPayload, InstanceRender, ProgressNode } from '@/types/instance'
import { feedback } from '@/utils/feedback'

const props = defineProps<{
  data: InstanceRender
  /** 管理员/设计者才看得到入口；服务端还会再校验一次 */
  canManage: boolean
}>()

const emit = defineEmits<{ updated: [InstanceRender] }>()

const AButton = Button

/** 机制 C 允许的控件（与服务端 EXT_FIELD_TYPES 一致） */
const ALLOWED_TYPES: FieldType[] = [
  'text',
  'textarea',
  'number',
  'date',
  'datetime',
  'select',
  'attachment',
]
const typeOptions = ALLOWED_TYPES.map((t) => ({ value: t, label: FIELD_TYPE_LABELS[t] }))

const open = ref(false)
const submitting = ref(false)

const label = ref('')
const type = ref<FieldType>('text')
const required = ref(false)
const editableNodes = ref<string[]>([])
const placeholder = ref('')
const options = ref<Array<{ label: string; value: string }>>([{ label: '', value: '' }])

const fields = computed(() => props.data.ext_fields ?? [])

/** 下拉选项里空行是常态（用户点了「添加选项」还没填），提交前过滤掉 */
const validOptions = computed(() =>
  options.value
    .filter((o) => o.label.trim())
    .map((o) => ({ label: o.label.trim(), value: (o.value.trim() || o.label.trim()) })),
)

function flattenNodes(nodes: ProgressNode[]): Array<{ value: string; label: string }> {
  const out: Array<{ value: string; label: string }> = []
  for (const node of nodes) {
    if (node.type === 'condition') {
      for (const branch of node.branches ?? []) out.push(...flattenNodes(branch.nodes ?? []))
      continue
    }
    if (node.type === 'parallel') {
      for (const member of node.members ?? []) out.push(...flattenNodes([member]))
      continue
    }
    if (node.type === 'approval' || node.type === 'fill') {
      out.push({ value: node.node_id, label: node.name })
    }
  }
  return out
}

const nodeOptions = computed(() => flattenNodes(props.data.progress ?? []))

const canSubmit = computed(() => {
  if (!label.value.trim()) return false
  if (type.value === 'select' && !validOptions.value.length) return false
  return true
})

function openModal(): void {
  label.value = ''
  type.value = 'text'
  required.value = false
  placeholder.value = ''
  options.value = [{ label: '', value: '' }]
  // 默认可编辑节点 = 当前待办节点（与服务端默认一致）
  editableNodes.value = props.data.current_node ? [props.data.current_node.node_id] : []
  open.value = true
}

async function submit(): Promise<void> {
  submitting.value = true
  const payload: ExtFieldPayload = {
    label: label.value.trim(),
    type: type.value,
    required: required.value,
    editable_node_ids: editableNodes.value,
    config: type.value === 'select' ? { options: validOptions.value } : {},
    placeholder: placeholder.value.trim() || null,
  }
  try {
    const fresh = await instanceApi.addExtField(props.data.instance.id, payload)
    feedback.success(`已追加字段「${payload.label}」，当前处理人已收到通知`)
    open.value = false
    emit('updated', fresh)
  } catch {
    // 拦截器已提示（类型不支持 / 无权限 / 实例已归档…）
  } finally {
    submitting.value = false
  }
}

async function disable(field: ExtFieldItem): Promise<void> {
  const ok = await feedback.confirm({
    title: `停用「${field.label}」？`,
    content: '停用后界面上不再出现，但历史数据与快照仍保留 —— 动态字段不可物理删除。',
    danger: true,
  })
  if (!ok) return
  try {
    const fresh = await instanceApi.disableExtField(props.data.instance.id, field.field_key)
    feedback.success('已停用')
    emit('updated', fresh)
  } catch {
    // 拦截器已提示
  }
}

function typeLabel(value: string): string {
  return FIELD_TYPE_LABELS[value as FieldType] ?? value
}
</script>

<template>
  <a-button v-if="canManage" @click="openModal">
    <template #icon><PlusOutlined /></template>
    追加字段
  </a-button>

  <a-modal
    v-model:open="open"
    title="运行中追加字段"
    :width="680"
    :confirm-loading="submitting"
    ok-text="追加"
    cancel-text="取消"
    :ok-button-props="{ disabled: !canSubmit }"
    @ok="submit"
  >
    <a-alert
      type="info"
      show-icon
      class="mb"
      message="只对这一张单生效，不改模板"
      description="追加后不可删除（只能停用）；默认只读，仅指定的节点可填，追加点之前的节点看不到它。"
    />

    <div v-if="fields.length" class="existing">
      <div class="block-title">本实例已有的动态字段</div>
      <div v-for="field in fields" :key="field.field_key" class="existing-row">
        <span class="field-label">{{ field.label }}</span>
        <a-tag>{{ typeLabel(field.type) }}</a-tag>
        <a-tag v-if="field.required" color="red">必填</a-tag>
        <span class="text-muted text-mono key">{{ field.field_key }}</span>
        <a-button size="small" type="link" danger @click="disable(field)">停用</a-button>
      </div>
      <a-divider />
    </div>

    <a-form layout="vertical">
      <a-form-item label="字段名称" required>
        <a-input v-model:value="label" :maxlength="64" placeholder="如：合同编号" />
      </a-form-item>

      <a-row :gutter="12">
        <a-col :span="12">
          <a-form-item label="控件类型">
            <a-select v-model:value="type" :options="typeOptions" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="必填">
            <a-switch v-model:checked="required" />
            <span class="text-muted hint">只在可编辑的节点上要求填</span>
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="可编辑节点" extra="不选则默认当前待办节点；其余节点一律只读">
        <a-select
          v-model:value="editableNodes"
          mode="multiple"
          :options="nodeOptions"
          placeholder="默认：当前待办节点"
        />
      </a-form-item>

      <a-form-item v-if="type === 'select'" label="下拉选项">
        <div v-for="(option, index) in options" :key="index" class="option-row">
          <a-input v-model:value="option.label" placeholder="显示名" />
          <a-input v-model:value="option.value" placeholder="值（留空同显示名）" />
          <a-button
            type="link"
            danger
            :disabled="options.length <= 1"
            @click="options.splice(index, 1)"
          >
            删除
          </a-button>
        </div>
        <a-button type="dashed" block @click="options.push({ label: '', value: '' })">
          添加选项
        </a-button>
      </a-form-item>

      <a-form-item label="占位提示（可选）">
        <a-input v-model:value="placeholder" :maxlength="128" placeholder="输入框里的灰色提示" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped lang="scss">
.mb {
  margin-bottom: 12px;
}

.block-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.existing-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.field-label {
  font-weight: 500;
}

.key {
  font-size: 12px;
}

.option-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}

.hint {
  margin-left: 8px;
  font-size: 12px;
}
</style>

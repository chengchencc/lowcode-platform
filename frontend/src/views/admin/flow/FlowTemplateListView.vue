<script setup lang="ts">
import {
  DeleteOutlined,
  EditOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { Button, Card, Input, Select, Space, Table, Tag, Tooltip } from 'ant-design-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { flowApi } from '@/api/modules/flow'
import { formApi } from '@/api/modules/form'
import type { FormTemplate } from '@/types/form'
import type { FlowStatus, FlowTemplate } from '@/types/flow'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const router = useRouter()

const rows = ref<FlowTemplate[]>([])
const forms = ref<FormTemplate[]>([])
const loading = ref(false)
const query = reactive({
  keyword: '',
  category: undefined as string | undefined,
  status: undefined as FlowStatus | undefined,
})

const columns = [
  { title: '流程名称', key: 'name', width: 200 },
  { title: '绑定表单', key: 'form', width: 160 },
  { title: '分类', key: 'category', width: 110 },
  { title: '节点数', key: 'node_count', width: 90 },
  { title: '当前版本', key: 'version', width: 180 },
  { title: '状态', key: 'status', width: 100 },
  { title: '更新时间', key: 'updated_at', width: 150 },
  // 四个操作都带图标 + 文字，固定宽度按实测留足，避免换行
  { title: '操作', key: 'action', width: 280, fixed: 'right' as const },
]

const STATUS_META: Record<FlowStatus, { text: string; color: string }> = {
  DRAFT: { text: '未发布', color: 'default' },
  PUBLISHED: { text: '已发布', color: 'green' },
  DISABLED: { text: '已停用', color: 'red' },
}

const categoryOptions = computed(() => {
  const set = new Set(rows.value.map((r) => r.category).filter(Boolean) as string[])
  return [...set].map((c) => ({ value: c, label: c }))
})

/** 只有「已发布」的表单能绑定到流程（发布流程时会锁定表单版本）。 */
const bindableForms = computed(() =>
  forms.value
    .filter((f) => f.status === 'PUBLISHED')
    .map((f) => ({ value: f.id, label: f.name })),
)

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await flowApi.listTemplates({
      keyword: query.keyword || undefined,
      category: query.category,
      status: query.status,
    })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  forms.value = await formApi.listTemplates()
  await load()
})

function resetQuery(): void {
  query.keyword = ''
  query.category = undefined
  query.status = undefined
  void load()
}

// --------------------------------------------------------------------------- 新建 / 编辑

const editorOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const isCreate = computed(() => editingId.value === null)

const form = reactive({
  name: '',
  code: '',
  category: '',
  description: '',
  form_template_id: undefined as number | undefined,
})
const formErrors = reactive<Record<string, string>>({})

/** 编辑态展示「当前绑定的是哪个表单」（绑定关系创建后不可改） */
const editingFormName = computed(
  () => rows.value.find((r) => r.id === editingId.value)?.form_template_name ?? '—',
)

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    name: '', code: '', category: '', description: '', form_template_id: undefined,
  })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  editorOpen.value = true
}

function openEdit(record: FlowTemplate): void {
  editingId.value = record.id
  Object.assign(form, {
    name: record.name,
    code: record.code ?? '',
    category: record.category ?? '',
    description: record.description ?? '',
    form_template_id: record.form_template_id,
  })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  editorOpen.value = true
}

async function submitEditor(): Promise<void> {
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  if (!form.name) formErrors.name = '请输入流程名称'
  if (isCreate.value && !form.form_template_id) formErrors.form_template_id = '请选择绑定的表单'

  if (Object.keys(formErrors).length) return

  saving.value = true
  try {
    if (isCreate.value) {
      const created = await flowApi.createTemplate({
        name: form.name,
        form_template_id: form.form_template_id as number,
        code: form.code || null,
        category: form.category || null,
        description: form.description || null,
      })
      editorOpen.value = false
      feedback.success('流程已创建，正在打开配置器')
      await load()
      await router.push({ name: 'flow-designer', params: { id: created.id } })
      return
    }
    await flowApi.updateTemplate(editingId.value as number, {
      name: form.name,
      category: form.category || null,
      description: form.description || null,
    })
    editorOpen.value = false
    feedback.success('已保存')
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.code === 'FLOW_CODE_EXISTS') {
      formErrors.code = error.message
    }
  } finally {
    saving.value = false
  }
}

// --------------------------------------------------------------------------- 行操作

async function removeTemplate(record: FlowTemplate): Promise<void> {
  const ok = await feedback.confirm({
    title: `确定删除流程「${record.name}」吗？`,
    content: '会一并移除全部版本，且不可恢复。',
    danger: true,
  })
  if (!ok) return
  await flowApi.deleteTemplate(record.id)
  feedback.success('已删除')
  await load()
}

async function toggleStatus(record: FlowTemplate): Promise<void> {
  const next: 'DRAFT' | 'DISABLED' = record.status === 'DISABLED' ? 'DRAFT' : 'DISABLED'
  if (next === 'DISABLED') {
    const ok = await feedback.confirm({
      title: `停用「${record.name}」？`,
      content: '停用后不能被新的流程引用，已有实例不受影响。',
      danger: true,
    })
    if (!ok) return
  }
  try {
    await flowApi.setTemplateStatus(record.id, next)
    feedback.success(next === 'DISABLED' ? '已停用' : '已恢复')
    await load()
  } catch (error) {
    if (error instanceof ApiError) feedback.error(error.message)
  }
}
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <div class="page-toolbar">
        <Space wrap>
          <Input.Search
            v-model:value="query.keyword"
            placeholder="流程名称或编码"
            style="width: 220px"
            allow-clear
            @search="load"
          />
          <Select
            v-model:value="query.category"
            :options="categoryOptions"
            placeholder="分类"
            style="width: 130px"
            allow-clear
          />
          <Select
            v-model:value="query.status"
            :options="[
              { value: 'DRAFT', label: '未发布' },
              { value: 'PUBLISHED', label: '已发布' },
              { value: 'DISABLED', label: '已停用' },
            ]"
            placeholder="状态"
            style="width: 120px"
            allow-clear
          />
          <Button type="primary" @click="load">查询</Button>
          <Button @click="resetQuery">重置</Button>
        </Space>

        <Button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建流程
        </Button>
      </div>

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1250 }"
        :pagination="{ pageSize: 20, showTotal: (total: number) => `共 ${total} 条流程` }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a @click="router.push({ name: 'flow-designer', params: { id: record.id } })">
              {{ record.name }}
            </a>
            <div v-if="record.description" class="text-muted desc">{{ record.description }}</div>
          </template>

          <template v-else-if="column.key === 'form'">
            <span v-if="record.form_template_name">{{ record.form_template_name }}</span>
            <span v-else class="text-muted">—</span>
          </template>

          <template v-else-if="column.key === 'category'">
            {{ record.category || '—' }}
          </template>

          <template v-else-if="column.key === 'node_count'">
            {{ record.node_count }}
          </template>

          <template v-else-if="column.key === 'version'">
            <template v-if="record.current_version_no != null">
              <Tag color="green">v{{ record.current_version_no }} 已发布</Tag>
              <div class="text-muted locked">
                锁定表单 v{{ record.locked_form_version_no }}
              </div>
            </template>
            <Tag v-if="record.draft_version_id" color="orange">有草稿</Tag>
            <span v-if="record.current_version_no == null && !record.draft_version_id" class="text-muted">
              —
            </span>
          </template>

          <template v-else-if="column.key === 'status'">
            <Tag :color="STATUS_META[record.status as FlowStatus].color">
              {{ STATUS_META[record.status as FlowStatus].text }}
            </Tag>
          </template>

          <template v-else-if="column.key === 'updated_at'">
            {{ formatDateTime(record.updated_at) }}
          </template>

          <template v-else-if="column.key === 'action'">
            <Space :size="2">
              <Tooltip title="打开流程设计器">
                <Button
                  type="link"
                  size="small"
                  @click="router.push({ name: 'flow-designer', params: { id: record.id } })"
                >
                  <template #icon><SettingOutlined /></template>
                  配置
                </Button>
              </Tooltip>
              <Tooltip title="修改名称、分类等基础信息">
                <Button type="link" size="small" @click="openEdit(record as FlowTemplate)">
                  <template #icon><EditOutlined /></template>
                  编辑
                </Button>
              </Tooltip>
              <Tooltip
                :title="
                  record.status === 'DISABLED'
                    ? '恢复后可以发起新单据'
                    : '停用后不能再发起新单据，已有实例不受影响'
                "
              >
                <Button
                  type="link"
                  size="small"
                  :danger="record.status !== 'DISABLED'"
                  @click="toggleStatus(record as FlowTemplate)"
                >
                  <template #icon>
                    <PlayCircleOutlined v-if="record.status === 'DISABLED'" />
                    <PauseCircleOutlined v-else />
                  </template>
                  {{ record.status === 'DISABLED' ? '恢复' : '停用' }}
                </Button>
              </Tooltip>
              <Tooltip title="删除流程及全部版本，不可恢复">
                <Button
                  type="link"
                  size="small"
                  danger
                  @click="removeTemplate(record as FlowTemplate)"
                >
                  <template #icon><DeleteOutlined /></template>
                  删除
                </Button>
              </Tooltip>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <a-modal
      v-model:open="editorOpen"
      :title="isCreate ? '新建流程' : '编辑流程信息'"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      :width="520"
      @ok="submitEditor"
    >
      <a-form layout="vertical">
        <a-form-item
          label="流程名称"
          required
          :validate-status="formErrors.name ? 'error' : undefined"
          :help="formErrors.name"
        >
          <Input v-model:value="form.name" placeholder="如：费用报销流程" />
        </a-form-item>

        <a-form-item
          v-if="isCreate"
          label="绑定表单"
          required
          :validate-status="formErrors.form_template_id ? 'error' : undefined"
          :help="formErrors.form_template_id || '只有已发布的表单可选'"
        >
          <Select
            v-model:value="form.form_template_id"
            :options="bindableForms"
            placeholder="选择表单模板"
            show-search
            option-filter-prop="label"
          />
        </a-form-item>
        <a-alert
          v-else
          type="info"
          show-icon
          class="form-hint"
          :message="`绑定的表单：${editingFormName}`"
          description="绑定关系创建后不可修改；要换表单请新建流程"
        />

        <a-form-item v-if="isCreate" label="流程编码" :validate-status="formErrors.code ? 'error' : undefined" :help="formErrors.code || '选填'">
          <Input v-model:value="form.code" placeholder="如：REIMBURSEMENT_FLOW" />
        </a-form-item>
        <a-form-item label="分类" help="选填，用于列表页归类">
          <Input v-model:value="form.category" placeholder="如：财务" />
        </a-form-item>
        <a-form-item label="说明">
          <a-textarea v-model:value="form.description" :rows="2" placeholder="选填" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.desc {
  font-size: 12px;
  margin-top: 2px;
}

.locked {
  font-size: 11px;
  margin-top: 2px;
}

.form-hint {
  margin-bottom: 16px;
}
</style>

<script setup lang="ts">
import {
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SettingOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import { Button, Card, Input, Select, Space, Table, Tag, Tooltip, Upload } from 'ant-design-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { formApi } from '@/api/modules/form'
import type { FormStatus, FormTemplate } from '@/types/form'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const router = useRouter()

const rows = ref<FormTemplate[]>([])
const groups = ref<string[]>([])
const loading = ref(false)
const query = reactive({
  keyword: '',
  group_name: undefined as string | undefined,
  status: undefined as FormStatus | undefined,
})

const columns = [
  { title: '表单名称', key: 'name', width: 220 },
  { title: '编码', key: 'code', width: 150 },
  { title: '分组', key: 'group_name', width: 110 },
  { title: '字段数', key: 'field_count', width: 90 },
  { title: '当前版本', key: 'version', width: 130 },
  { title: '状态', key: 'status', width: 100 },
  { title: '更新时间', key: 'updated_at', width: 150 },
  // 六个操作都带图标 + 文字，固定宽度按实测留足，避免换行
  { title: '操作', key: 'action', width: 420, fixed: 'right' as const },
]

const STATUS_META: Record<FormStatus, { text: string; color: string }> = {
  DRAFT: { text: '未发布', color: 'default' },
  PUBLISHED: { text: '已发布', color: 'green' },
  DISABLED: { text: '已停用', color: 'red' },
}

const groupOptions = computed(() => groups.value.map((g) => ({ value: g, label: g })))

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await formApi.listTemplates({
      keyword: query.keyword || undefined,
      group_name: query.group_name,
      status: query.status,
    })
  } finally {
    loading.value = false
  }
}

async function loadGroups(): Promise<void> {
  groups.value = await formApi.groups()
}

onMounted(async () => {
  await Promise.all([load(), loadGroups()])
})

function resetQuery(): void {
  query.keyword = ''
  query.group_name = undefined
  query.status = undefined
  void load()
}

// --------------------------------------------------------------------------- 新建 / 编辑

const editorOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
/** 正在编辑的模板是否已有编码：已有则不可改，未设置才允许补录 */
const editingHasCode = ref(false)
const isCreate = computed(() => editingId.value === null)

const form = reactive({ name: '', code: '', group_name: '', description: '' })
const formErrors = reactive<Record<string, string>>({})

function openCreate(): void {
  editingId.value = null
  editingHasCode.value = false
  Object.assign(form, { name: '', code: '', group_name: '', description: '' })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  editorOpen.value = true
}

function openEdit(record: FormTemplate): void {
  editingId.value = record.id
  editingHasCode.value = !!record.code
  Object.assign(form, {
    name: record.name,
    code: record.code ?? '',
    group_name: record.group_name ?? '',
    description: record.description ?? '',
  })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  editorOpen.value = true
}

async function submitEditor(): Promise<void> {
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  if (!form.name) formErrors.name = '请输入表单名称'
  if (Object.keys(formErrors).length) return

  saving.value = true
  try {
    const payload = {
      name: form.name,
      group_name: form.group_name || null,
      description: form.description || null,
    }
    if (isCreate.value) {
      const created = await formApi.createTemplate({
        ...payload,
        code: form.code || null,
      })
      editorOpen.value = false
      feedback.success('表单已创建，正在打开设计器')
      await load()
      // 新建后直接进设计器 —— 刚建完表单下一步必然是配字段
      await router.push({ name: 'form-designer', params: { id: created.id } })
      return
    }
    await formApi.updateTemplate(editingId.value as number, {
      ...payload,
      // 已设置的编码不可改，不必回传；未设置时允许补录
      ...(editingHasCode.value ? {} : { code: form.code || null }),
    })
    editorOpen.value = false
    feedback.success('已保存')
    await Promise.all([load(), loadGroups()])
  } catch (error) {
    if (
      error instanceof ApiError &&
      (error.code === 'FORM_CODE_EXISTS' || error.code === 'FORM_CODE_IMMUTABLE')
    ) {
      formErrors.code = error.message
    }
  } finally {
    saving.value = false
  }
}

// --------------------------------------------------------------------------- 行操作

async function copyTemplate(record: FormTemplate): Promise<void> {
  const name = window.prompt('新表单名称', `${record.name} 副本`)
  if (!name) return
  try {
    await formApi.copyTemplate(record.id, name, null)
    feedback.success('已复制')
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function removeTemplate(record: FormTemplate): Promise<void> {
  const ok = await feedback.confirm({
    title: `确定删除表单「${record.name}」吗？`,
    content:
      record.current_version_no != null
        ? '该表单已有发布版本。删除会一并移除全部版本，且不可恢复。'
        : '会一并移除全部草稿版本，且不可恢复。',
    danger: true,
  })
  if (!ok) return
  await formApi.deleteTemplate(record.id)
  feedback.success('已删除')
  await Promise.all([load(), loadGroups()])
}

async function toggleStatus(record: FormTemplate): Promise<void> {
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
    await formApi.setTemplateStatus(record.id, next)
    feedback.success(next === 'DISABLED' ? '已停用' : '已恢复')
    await load()
  } catch (error) {
    if (error instanceof ApiError) feedback.error(error.message)
  }
}

// --------------------------------------------------------------------------- 导入导出

async function exportTemplate(record: FormTemplate): Promise<void> {
  const data = await formApi.exportTemplate(record.id)
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${record.name}.json`
  link.click()
  URL.revokeObjectURL(url)
}

const importing = ref(false)

/** 交给 Upload 的 beforeUpload：读文件内容后手动调接口 */
async function handleImportFile(file: File): Promise<boolean> {
  importing.value = true
  try {
    const text = await file.text()
    const payload = JSON.parse(text) as Record<string, unknown>
    // 导入时清掉编码，避免与已有表单冲突；需要时可在列表「编辑」里补录
    await formApi.importTemplate({ ...payload, code: null })
    feedback.success('导入成功')
    await Promise.all([load(), loadGroups()])
  } catch (error) {
    if (error instanceof SyntaxError) feedback.error('文件不是合法的 JSON')
    // 其他错误已由拦截器提示
  } finally {
    importing.value = false
  }
  return false
}
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <div class="page-toolbar">
        <Space wrap>
          <Input.Search
            v-model:value="query.keyword"
            placeholder="表单名称或编码"
            style="width: 220px"
            allow-clear
            @search="load"
          />
          <Select
            v-model:value="query.group_name"
            :options="groupOptions"
            placeholder="分组"
            style="width: 140px"
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

        <Space>
          <Upload
            :before-upload="handleImportFile"
            :show-upload-list="false"
            accept=".json,application/json"
          >
            <Button :loading="importing">
              <template #icon><UploadOutlined /></template>
              导入 JSON
            </Button>
          </Upload>
          <Button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新建表单
          </Button>
        </Space>
      </div>

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1400 }"
        :pagination="{ pageSize: 20, showTotal: (total: number) => `共 ${total} 个表单` }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a @click="router.push({ name: 'form-designer', params: { id: record.id } })">
              {{ record.name }}
            </a>
            <div v-if="record.description" class="text-muted desc">{{ record.description }}</div>
          </template>

          <template v-else-if="column.key === 'code'">
            <span v-if="record.code" class="text-mono">{{ record.code }}</span>
            <span v-else class="text-muted">—</span>
          </template>

          <template v-else-if="column.key === 'group_name'">
            {{ record.group_name || '—' }}
          </template>

          <template v-else-if="column.key === 'field_count'">
            {{ record.field_count }}
          </template>

          <template v-else-if="column.key === 'version'">
            <template v-if="record.current_version_no != null">
              <Tag color="green">v{{ record.current_version_no }} 已发布</Tag>
            </template>
            <Tag v-if="record.draft_version_id" color="orange">有草稿</Tag>
            <span v-if="record.current_version_no == null && !record.draft_version_id" class="text-muted">
              —
            </span>
          </template>

          <template v-else-if="column.key === 'status'">
            <Tag :color="STATUS_META[record.status as FormStatus].color">
              {{ STATUS_META[record.status as FormStatus].text }}
            </Tag>
          </template>

          <template v-else-if="column.key === 'updated_at'">
            {{ formatDateTime(record.updated_at) }}
          </template>

          <template v-else-if="column.key === 'action'">
            <Space :size="2">
              <Tooltip title="打开表单设计器">
                <Button
                  type="link"
                  size="small"
                  @click="router.push({ name: 'form-designer', params: { id: record.id } })"
                >
                  <template #icon><SettingOutlined /></template>
                  设计
                </Button>
              </Tooltip>
              <Tooltip title="修改名称、分组等基础信息">
                <Button type="link" size="small" @click="openEdit(record as FormTemplate)">
                  <template #icon><EditOutlined /></template>
                  编辑
                </Button>
              </Tooltip>
              <Tooltip title="以当前表单为模板新建一份">
                <Button type="link" size="small" @click="copyTemplate(record as FormTemplate)">
                  <template #icon><CopyOutlined /></template>
                  复制
                </Button>
              </Tooltip>
              <Tooltip title="导出为 JSON 文件，可用于导入">
                <Button type="link" size="small" @click="exportTemplate(record as FormTemplate)">
                  <template #icon><DownloadOutlined /></template>
                  导出
                </Button>
              </Tooltip>
              <Tooltip
                :title="
                  record.status === 'DISABLED'
                    ? '恢复后可被新流程引用'
                    : '停用后不能被新流程引用，已有实例不受影响'
                "
              >
                <Button
                  type="link"
                  size="small"
                  :danger="record.status !== 'DISABLED'"
                  @click="toggleStatus(record as FormTemplate)"
                >
                  <template #icon>
                    <PlayCircleOutlined v-if="record.status === 'DISABLED'" />
                    <PauseCircleOutlined v-else />
                  </template>
                  {{ record.status === 'DISABLED' ? '恢复' : '停用' }}
                </Button>
              </Tooltip>
              <Tooltip title="删除表单及全部版本，不可恢复">
                <Button
                  type="link"
                  size="small"
                  danger
                  @click="removeTemplate(record as FormTemplate)"
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
      :title="isCreate ? '新建表单' : '编辑表单信息'"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitEditor"
    >
      <a-form layout="vertical">
        <a-form-item
          label="表单名称"
          required
          :validate-status="formErrors.name ? 'error' : undefined"
          :help="formErrors.name"
        >
          <Input v-model:value="form.name" placeholder="如：费用报销单" />
        </a-form-item>
        <a-form-item
          v-if="isCreate || !editingHasCode"
          label="表单编码"
          :validate-status="formErrors.code ? 'error' : undefined"
          :help="
            formErrors.code ||
            (isCreate
              ? '选填，用于导入导出与人工引用；设置后不可修改'
              : '当前未设置，可补录；设置后不可修改')
          "
        >
          <Input v-model:value="form.code" placeholder="如：REIMBURSEMENT" />
        </a-form-item>
        <a-form-item label="分组" help="可选已有分组，也可直接输入新分组名">
          <!-- AutoComplete 而不是 Select：Select 不能输入选项之外的新值 -->
          <a-auto-complete
            v-model:value="form.group_name"
            :options="groupOptions"
            placeholder="选填，用于列表页归类"
            allow-clear
          />
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
</style>

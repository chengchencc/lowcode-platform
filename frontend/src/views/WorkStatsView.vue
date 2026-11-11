<script setup lang="ts">
import { PlusOutlined } from '@ant-design/icons-vue'
import {
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
} from 'ant-design-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { userApi } from '@/api/modules/user'
import { workStatApi } from '@/api/modules/workStat'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import type { WorkStatColumn, WorkStatScope, WorkStatSheet } from '@/types/workStat'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const router = useRouter()
const auth = useAuthStore()
const org = useOrgStore()

const sheets = ref<WorkStatSheet[]>([])
const loading = ref(false)

const COLUMN_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'select', label: '下拉' },
]

function emptyScope(): WorkStatScope {
  return { roles: [], depts: [], users: [] }
}

const form = reactive({
  name: '',
  description: '',
  columns: [] as WorkStatColumn[],
  viewerAll: true,
  viewerScope: emptyScope(),
  editorAll: true,
  editorScope: emptyScope(),
})

const editorOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const isCreate = computed(() => editingId.value === null)

const roleOptions = computed(() => org.roles.map((role) => ({ value: role.code, label: role.name })))
const deptOptions = computed(() => org.flatDepts().map((dept) => ({ value: dept.value, label: dept.label })))
const userOptions = ref<Array<{ value: number; label: string }>>([])

function newColumn(index: number): WorkStatColumn {
  return {
    key: `c_${Date.now()}_${index}`,
    label: '',
    type: 'text',
    width: 120,
    required: false,
    options: [],
  }
}

function addColumn(): void {
  form.columns.push(newColumn(form.columns.length))
}

function removeColumn(index: number): void {
  form.columns.splice(index, 1)
}

function resetForm(): void {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.columns = [
    { key: 'c_name', label: '姓名', type: 'text', width: 120, required: true, options: [] },
    { key: 'c_date', label: '日期', type: 'date', width: 120, required: false, options: [] },
    { key: 'c_hours', label: '工时', type: 'number', width: 100, required: false, options: [] },
  ]
  form.viewerAll = true
  form.viewerScope = emptyScope()
  form.editorAll = true
  form.editorScope = emptyScope()
}

async function load(): Promise<void> {
  loading.value = true
  try {
    sheets.value = await workStatApi.listSheets()
  } finally {
    loading.value = false
  }
}

async function loadOptions(): Promise<void> {
  await Promise.all([org.loadRoles(), org.loadDeptTree()])
  try {
    const users = await userApi.options({ limit: 200 })
    userOptions.value = users.map((user) => ({
      value: user.id,
      label: `${user.real_name}${user.dept_name ? `（${user.dept_name}）` : ''}`,
    }))
  } catch {
    // 人员范围是选填；加载失败不影响表配置
  }
}

async function openCreate(): Promise<void> {
  resetForm()
  editorOpen.value = true
  await loadOptions()
}

async function openEdit(record: WorkStatSheet): Promise<void> {
  editingId.value = record.id
  form.name = record.name
  form.description = record.description ?? ''
  form.columns = record.columns.map((column) => ({ ...column, options: [...column.options] }))
  form.viewerAll = record.viewer_scope === null
  form.viewerScope = record.viewer_scope
    ? { ...record.viewer_scope, roles: [...record.viewer_scope.roles], depts: [...record.viewer_scope.depts], users: [...record.viewer_scope.users] }
    : emptyScope()
  form.editorAll = record.editor_scope === null
  form.editorScope = record.editor_scope
    ? { ...record.editor_scope, roles: [...record.editor_scope.roles], depts: [...record.editor_scope.depts], users: [...record.editor_scope.users] }
    : emptyScope()
  editorOpen.value = true
  await loadOptions()
}

async function submit(): Promise<void> {
  if (!form.name.trim()) {
    feedback.error('请输入统计表名称')
    return
  }
  if (!form.columns.length) {
    feedback.error('至少配置一列')
    return
  }
  const labels = form.columns.map((column) => column.label.trim())
  if (labels.some((label) => !label)) {
    feedback.error('列名不能为空')
    return
  }
  if (new Set(labels).size !== labels.length) {
    feedback.error('列名不能重复')
    return
  }

  const payload = {
    name: form.name.trim(),
    description: form.description || null,
    columns: form.columns.map((column) => ({
      ...column,
      label: column.label.trim(),
      options: column.type === 'select' ? column.options : [],
    })),
    viewer_scope: form.viewerAll ? null : form.viewerScope,
    editor_scope: form.editorAll ? null : form.editorScope,
  }

  saving.value = true
  try {
    if (isCreate.value) {
      await workStatApi.createSheet(payload)
      feedback.success('统计表已创建')
    } else {
      await workStatApi.updateSheet(editingId.value as number, payload)
      feedback.success('已保存')
    }
    editorOpen.value = false
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.code === 'WORK_STAT_LABEL_DUPLICATE') {
      feedback.error(error.message)
    }
  } finally {
    saving.value = false
  }
}

async function remove(record: WorkStatSheet): Promise<void> {
  const ok = await feedback.confirm({
    title: `删除统计表「${record.name}」？`,
    content: '表内所有数据和修改历史会一起删除，不可恢复。',
    danger: true,
  })
  if (!ok) return
  await workStatApi.deleteSheet(record.id)
  feedback.success('已删除')
  await load()
}

function openSheet(record: WorkStatSheet): void {
  void router.push({ name: 'work-stat-sheet', params: { id: record.id } })
}

const columns = [
  { title: '名称', key: 'name', width: 220 },
  { title: '说明', key: 'description' },
  { title: '列数', key: 'column_count', width: 80 },
  { title: '可编辑', key: 'can_edit', width: 90 },
  { title: '更新时间', key: 'updated_at', width: 170 },
  { title: '操作', key: 'action', width: 200 },
]

onMounted(load)
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <template #title>工作量统计</template>
      <template #extra>
        <Button v-if="auth.isAdmin" type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建统计表
        </Button>
      </template>

      <Table
        v-if="sheets.length"
        :columns="columns"
        :data-source="sheets"
        row-key="id"
        size="middle"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a @click="openSheet(record as WorkStatSheet)">{{ record.name }}</a>
          </template>
          <template v-else-if="column.key === 'description'">
            {{ record.description || '—' }}
          </template>
          <template v-else-if="column.key === 'column_count'">
            {{ record.columns.length }}
          </template>
          <template v-else-if="column.key === 'can_edit'">
            <Tag :color="record.can_edit ? 'green' : 'default'">
              {{ record.can_edit ? '可编辑' : '只读' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'updated_at'">
            {{ formatDateTime(record.updated_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <Space :size="2">
              <Button type="link" size="small" @click="openSheet(record as WorkStatSheet)">
                打开
              </Button>
              <template v-if="auth.isAdmin">
                <Button type="link" size="small" @click="openEdit(record as WorkStatSheet)">
                  编辑
                </Button>
                <Button type="link" size="small" danger @click="remove(record as WorkStatSheet)">
                  删除
                </Button>
              </template>
            </Space>
          </template>
        </template>
      </Table>
      <Empty v-else description="还没有可查看的统计表" />
    </Card>

    <Modal
      v-model:open="editorOpen"
      :title="isCreate ? '新建统计表' : '编辑统计表'"
      :confirm-loading="saving"
      width="900px"
      ok-text="保存"
      cancel-text="取消"
      @ok="submit"
    >
      <div class="form-block">
        <div class="form-row">
          <label class="form-label">名称</label>
          <Input v-model:value="form.name" placeholder="如：部门月度工作量" />
        </div>
        <div class="form-row">
          <label class="form-label">说明</label>
          <Input v-model:value="form.description" placeholder="选填" />
        </div>
      </div>

      <div class="section-title">
        列配置
        <Button type="link" size="small" @click="addColumn">
          <template #icon><PlusOutlined /></template>
          添加列
        </Button>
      </div>
      <div class="column-rows">
        <div v-for="(column, index) in form.columns" :key="column.key" class="column-row">
          <Input v-model:value="column.label" placeholder="列名" class="col-label" />
          <Select v-model:value="column.type" :options="COLUMN_TYPES" class="col-type" />
          <Select
            v-if="column.type === 'select'"
            v-model:value="column.options"
            mode="tags"
            placeholder="输入选项后回车"
            class="col-options"
          />
          <Switch
            v-model:checked="column.required"
            checked-children="必填"
            un-checked-children="选填"
            class="col-required"
          />
          <Button type="link" size="small" danger @click="removeColumn(index)">删除</Button>
        </div>
      </div>

      <div class="section-title">可见范围</div>
      <div class="scope-row">
        <Switch
          v-model:checked="form.viewerAll"
          checked-children="所有人可见"
          un-checked-children="指定范围"
        />
        <template v-if="!form.viewerAll">
          <Select v-model:value="form.viewerScope.roles" mode="multiple" :options="roleOptions" placeholder="角色" class="scope-select" />
          <Select v-model:value="form.viewerScope.depts" mode="multiple" :options="deptOptions" placeholder="部门" class="scope-select" />
          <Select v-model:value="form.viewerScope.users" mode="multiple" :options="userOptions" placeholder="人员" show-search option-filter-prop="label" class="scope-select" />
        </template>
      </div>

      <div class="section-title">编辑范围</div>
      <div class="scope-row">
        <Switch
          v-model:checked="form.editorAll"
          checked-children="仅管理员可编辑"
          un-checked-children="指定可编辑人"
        />
        <template v-if="!form.editorAll">
          <Select v-model:value="form.editorScope.roles" mode="multiple" :options="roleOptions" placeholder="角色" class="scope-select" />
          <Select v-model:value="form.editorScope.depts" mode="multiple" :options="deptOptions" placeholder="部门" class="scope-select" />
          <Select v-model:value="form.editorScope.users" mode="multiple" :options="userOptions" placeholder="人员" show-search option-filter-prop="label" class="scope-select" />
        </template>
      </div>
    </Modal>
  </div>
</template>

<style scoped lang="scss">
.form-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-label {
  flex: 0 0 48px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 18px 0 8px;
  font-size: 13px;
  font-weight: 600;
}

.column-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.column-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.col-label {
  width: 140px;
}

.col-type {
  width: 96px;
}

.col-options {
  flex: 1;
  min-width: 160px;
}

.col-required {
  flex: 0 0 auto;
}

.scope-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.scope-select {
  min-width: 180px;
  flex: 1;
}
</style>

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

import { spreadsheetApi } from '@/api/modules/spreadsheet'
import { userApi } from '@/api/modules/user'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import type { SpreadsheetScope, SpreadsheetWorkbook } from '@/types/spreadsheet'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const router = useRouter()
const auth = useAuthStore()
const org = useOrgStore()

const rows = ref<SpreadsheetWorkbook[]>([])
const loading = ref(false)
const roleOptions = computed(() => org.roles.map((role) => ({ value: role.code, label: role.name })))
const deptOptions = computed(() => org.flatDepts().map((dept) => ({ value: dept.value, label: dept.label })))
const userOptions = ref<Array<{ value: number; label: string }>>([])

const editorOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const isCreate = computed(() => editingId.value === null)

const form = reactive({
  name: '',
  description: '',
  viewerAll: false,
  viewerScope: { all: false, roles: [], depts: [], users: [] } as SpreadsheetScope,
  editorAll: false,
  editorScope: { all: false, roles: [], depts: [], users: [] } as SpreadsheetScope,
})

function emptyScope(): SpreadsheetScope {
  return { all: false, roles: [], depts: [], users: [] }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await spreadsheetApi.list()
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
    // 人员范围选填
  }
}

function resetForm(): void {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.viewerAll = false
  form.viewerScope = emptyScope()
  form.editorAll = false
  form.editorScope = emptyScope()
}

async function openCreate(): Promise<void> {
  resetForm()
  editorOpen.value = true
  await loadOptions()
}

async function openEdit(record: SpreadsheetWorkbook): Promise<void> {
  editingId.value = record.id
  form.name = record.name
  form.description = record.description ?? ''
  form.viewerAll = !!record.viewer_scope?.all
  form.viewerScope = record.viewer_scope
    ? { ...record.viewer_scope, roles: [...record.viewer_scope.roles], depts: [...record.viewer_scope.depts], users: [...record.viewer_scope.users] }
    : emptyScope()
  form.editorAll = !!record.editor_scope?.all
  form.editorScope = record.editor_scope
    ? { ...record.editor_scope, roles: [...record.editor_scope.roles], depts: [...record.editor_scope.depts], users: [...record.editor_scope.users] }
    : emptyScope()
  editorOpen.value = true
  await loadOptions()
}

async function submit(): Promise<void> {
  if (!form.name.trim()) {
    feedback.error('请输入工作簿名称')
    return
  }
  const payload = {
    name: form.name.trim(),
    description: form.description || null,
    viewer_scope: form.viewerAll ? { ...emptyScope(), all: true } : form.viewerScope,
    editor_scope: form.editorAll ? { ...emptyScope(), all: true } : form.editorScope,
  }
  saving.value = true
  try {
    if (isCreate.value) {
      const created = await spreadsheetApi.create(payload)
      feedback.success('工作簿已创建')
      editorOpen.value = false
      await router.push({ name: 'spreadsheet', params: { id: created.id } })
      return
    }
    await spreadsheetApi.update(editingId.value as number, payload)
    feedback.success('已保存')
    editorOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(record: SpreadsheetWorkbook): Promise<void> {
  const ok = await feedback.confirm({
    title: `删除工作簿「${record.name}」？`,
    content: '工作簿内的所有内容会一起删除，不可恢复。',
    danger: true,
  })
  if (!ok) return
  await spreadsheetApi.remove(record.id)
  feedback.success('已删除')
  await load()
}

function open(record: SpreadsheetWorkbook): void {
  void router.push({ name: 'spreadsheet', params: { id: record.id } })
}

function canManage(record: SpreadsheetWorkbook): boolean {
  return auth.isAdmin || record.created_by === auth.user?.id
}

const columns = [
  { title: '名称', key: 'name', dataIndex: 'name', width: 240 },
  { title: '说明', key: 'description', dataIndex: 'description' },
  { title: '创建人', key: 'created_by_name', dataIndex: 'created_by_name', width: 120 },
  { title: '最后修改', key: 'updated_at', width: 180 },
  { title: '权限', key: 'access', width: 100 },
  { title: '操作', key: 'action', width: 160 },
]

onMounted(load)
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <template #title>共享表格</template>
      <template #extra>
        <Button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建工作簿
        </Button>
      </template>

      <Table
        v-if="rows.length"
        :columns="columns"
        :data-source="rows"
        row-key="id"
        size="middle"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a @click="open(record as SpreadsheetWorkbook)">{{ record.name }}</a>
          </template>
          <template v-else-if="column.key === 'description'">
            {{ record.description || '—' }}
          </template>
          <template v-else-if="column.key === 'updated_at'">
            {{ formatDateTime(record.updated_at) }}
          </template>
          <template v-else-if="column.key === 'access'">
            <Tag :color="record.can_edit ? 'green' : 'default'">
              {{ record.can_edit ? '可编辑' : '只读' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space :size="2">
              <Button type="link" size="small" @click="open(record as SpreadsheetWorkbook)">
                打开
              </Button>
              <template v-if="canManage(record as SpreadsheetWorkbook)">
                <Button type="link" size="small" @click="openEdit(record as SpreadsheetWorkbook)">
                  共享
                </Button>
                <Button
                  type="link"
                  size="small"
                  danger
                  @click="remove(record as SpreadsheetWorkbook)"
                >
                  删除
                </Button>
              </template>
            </Space>
          </template>
        </template>
      </Table>
      <Empty v-else description="还没有共享表格，点右上角新建一个" />
    </Card>

    <Modal
      v-model:open="editorOpen"
      :title="isCreate ? '新建工作簿' : '工作簿设置'"
      :confirm-loading="saving"
      width="760px"
      ok-text="保存"
      cancel-text="取消"
      @ok="submit"
    >
      <div class="form-row">
        <span class="label">名称</span>
        <Input v-model:value="form.name" placeholder="如：部门月度工作量" class="control" />
      </div>
      <div class="form-row">
        <span class="label">说明</span>
        <Input v-model:value="form.description" placeholder="选填" class="control" />
      </div>

      <div class="section-title">查看范围</div>
      <div class="scope-row">
        <Switch v-model:checked="form.viewerAll" checked-children="所有人可见" un-checked-children="指定范围" />
        <template v-if="!form.viewerAll">
          <Select v-model:value="form.viewerScope.roles" mode="multiple" :options="roleOptions" placeholder="角色" class="scope-select" />
          <Select v-model:value="form.viewerScope.depts" mode="multiple" :options="deptOptions" placeholder="部门" class="scope-select" />
          <Select v-model:value="form.viewerScope.users" mode="multiple" :options="userOptions" placeholder="人员" show-search option-filter-prop="label" class="scope-select" />
        </template>
      </div>

      <div class="section-title">编辑范围</div>
      <div class="scope-row">
        <Switch v-model:checked="form.editorAll" checked-children="所有人可编辑" un-checked-children="指定可编辑人" />
        <template v-if="!form.editorAll">
          <Select v-model:value="form.editorScope.roles" mode="multiple" :options="roleOptions" placeholder="角色" class="scope-select" />
          <Select v-model:value="form.editorScope.depts" mode="multiple" :options="deptOptions" placeholder="部门" class="scope-select" />
          <Select v-model:value="form.editorScope.users" mode="multiple" :options="userOptions" placeholder="人员" show-search option-filter-prop="label" class="scope-select" />
        </template>
      </div>
      <div class="text-muted hint">创建者和管理员始终可编辑；不选任何范围时仅创建者可见。</div>
    </Modal>
  </div>
</template>

<style scoped lang="scss">
.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.label {
  flex: 0 0 56px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.control {
  flex: 1;
}

.section-title {
  margin: 16px 0 8px;
  font-size: 13px;
  font-weight: 600;
}

.scope-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.scope-select {
  min-width: 170px;
  flex: 1;
}

.hint {
  margin-top: 10px;
  font-size: 12px;
}
</style>

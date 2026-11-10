<script setup lang="ts">
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/api/http'
import { userApi } from '@/api/modules/user'
import { useOrgStore } from '@/stores/org'
import type { UserInput, UserItem, UserStatus } from '@/types/org'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'


const org = useOrgStore()

// --------------------------------------------------------------------------- 列表

const rows = ref<UserItem[]>([])
const loading = ref(false)
const query = reactive({
  keyword: '',
  dept_id: null as number | null,
  include_sub_depts: false,
  // undefined 而非 null：antd Select 清空时回传 undefined，且不接受 null 作为 value
  status: undefined as UserStatus | undefined,
})
const paging = reactive({ page: 1, size: 20, total: 0 })

const columns = [
  { title: '用户名', dataIndex: 'username', key: 'username', width: 150 },
  { title: '姓名', dataIndex: 'real_name', key: 'real_name', width: 120 },
  { title: '部门', dataIndex: 'dept_name', key: 'dept_name', width: 140 },
  { title: '职位', dataIndex: 'position', key: 'position', width: 130 },
  { title: '角色', key: 'roles', width: 200 },
  { title: '联系方式', key: 'contact', width: 190 },
  { title: '状态', key: 'status', width: 80 },
  { title: '最后登录', key: 'last_login_at', width: 150 },
  { title: '操作', key: 'action', width: 210, fixed: 'right' as const },
]

const deptTreeData = computed(() => org.deptTree)

const deptFieldNames = { children: 'children', label: 'name', value: 'id' }

const roleOptions = computed(() => org.roles.map((r) => ({ value: r.id, label: r.name })))

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await userApi.list({
      page: paging.page,
      size: paging.size,
      keyword: query.keyword || undefined,
      dept_id: query.dept_id ?? undefined,
      include_sub_depts: query.include_sub_depts,
      status: query.status,
    })
    rows.value = data.items
    paging.total = data.total
  } finally {
    loading.value = false
  }
}

function search(): void {
  paging.page = 1
  void load()
}

function resetQuery(): void {
  query.keyword = ''
  query.dept_id = null
  query.include_sub_depts = false
  query.status = undefined
  search()
}

function onTableChange(pagination: { current?: number; pageSize?: number }): void {
  paging.page = pagination.current ?? 1
  paging.size = pagination.pageSize ?? 20
  void load()
}

onMounted(async () => {
  // 角色可能刚在角色管理里新建/改名；用户页强制刷新一次，避免拿到缓存旧列表
  await Promise.all([org.loadDeptTree(), org.loadRoles(true)])
  await load()
})

// --------------------------------------------------------------------------- 新建 / 编辑

const editorOpen = ref(false)
const editorSaving = ref(false)
const editingId = ref<number | null>(null)
const isCreate = computed(() => editingId.value === null)

const form = reactive({
  username: '',
  password: '',
  real_name: '',
  email: '',
  phone: '',
  dept_id: null as number | null,
  position: '',
  status: 'ACTIVE' as UserStatus,
  role_ids: [] as number[],
})
const formErrors = reactive<Record<string, string>>({})

function resetForm(): void {
  Object.assign(form, {
    username: '',
    password: '',
    real_name: '',
    email: '',
    phone: '',
    dept_id: null,
    position: '',
    status: 'ACTIVE',
    role_ids: [],
  })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
}

function openCreate(): void {
  editingId.value = null
  resetForm()
  editorOpen.value = true
}

function openEdit(record: UserItem): void {
  editingId.value = record.id
  resetForm()
  Object.assign(form, {
    username: record.username,
    real_name: record.real_name,
    email: record.email ?? '',
    phone: record.phone ?? '',
    dept_id: record.dept_id ?? null,
    position: record.position ?? '',
    status: record.status,
    role_ids: record.roles.map((r) => r.id),
  })
  editorOpen.value = true
}

function validate(): boolean {
  Object.keys(formErrors).forEach((k) => delete formErrors[k])

  if (isCreate.value) {
    if (!form.username) formErrors.username = '请输入用户名'
    else if (!/^[A-Za-z0-9_.-]{2,64}$/.test(form.username)) {
      formErrors.username = '仅允许字母、数字、下划线、点、短横线，至少 2 位'
    }
    if (form.password.length < 6) formErrors.password = '密码至少 6 位'
  }
  if (!form.real_name) formErrors.real_name = '请输入姓名'

  return Object.keys(formErrors).length === 0
}

async function submitEditor(): Promise<void> {
  if (!validate()) return

  const payload: UserInput = {
    real_name: form.real_name,
    email: form.email || null,
    phone: form.phone || null,
    dept_id: form.dept_id,
    position: form.position || null,
    status: form.status,
    role_ids: form.role_ids,
  }

  editorSaving.value = true
  try {
    if (isCreate.value) {
      await userApi.create({ ...payload, username: form.username, password: form.password })
      feedback.success('用户已创建')
    } else {
      await userApi.update(editingId.value as number, payload)
      feedback.success('用户已更新')
    }
    editorOpen.value = false
    await Promise.all([load(), org.loadDeptTree(true)])
  } catch (error) {
    applyServerErrors(error)
  } finally {
    editorSaving.value = false
  }
}

/** 把后端的字段级校验错误映射到表单上。 */
function applyServerErrors(error: unknown): void {
  if (!(error instanceof ApiError)) return
  if (error.code === 'USERNAME_EXISTS') formErrors.username = error.message
  else if (error.code === 'EMAIL_EXISTS') formErrors.email = error.message
  else if (error.code === 'ROLE_NOT_FOUND') formErrors.role_ids = error.message
}

// --------------------------------------------------------------------------- 重置密码

const passwordOpen = ref(false)
const passwordSaving = ref(false)
const passwordTarget = ref<UserItem | null>(null)
const passwordValue = ref('')
const passwordError = ref('')

function openResetPassword(record: UserItem): void {
  passwordTarget.value = record
  passwordValue.value = ''
  passwordError.value = ''
  passwordOpen.value = true
}

async function submitResetPassword(): Promise<void> {
  passwordError.value = ''
  if (passwordValue.value.length < 6) {
    passwordError.value = '密码至少 6 位'
    return
  }
  passwordSaving.value = true
  try {
    await userApi.resetPassword(passwordTarget.value!.id, passwordValue.value)
    passwordOpen.value = false
    feedback.success('密码已重置，该用户需重新登录')
    await load()
  } finally {
    passwordSaving.value = false
  }
}

// --------------------------------------------------------------------------- 启停 / 删除

const togglingId = ref<number | null>(null)

async function toggleStatus(record: UserItem): Promise<void> {
  const next: UserStatus = record.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'
  if (next === 'DISABLED') {
    const ok = await feedback.confirm({
      title: `确定停用「${record.real_name}」吗？`,
      content: '停用后该用户将无法登录，已登录的会话也会立即失效。',
      danger: true,
    })
    if (!ok) return
  }
  togglingId.value = record.id
  try {
    await userApi.setStatus(record.id, next)
    feedback.success(next === 'ACTIVE' ? '已启用' : '已停用')
    await load()
  } finally {
    togglingId.value = null
  }
}

async function removeUser(record: UserItem): Promise<void> {
  const ok = await feedback.confirm({
    title: `确定删除「${record.real_name}」吗？`,
    content: '该操作不可撤销。若只是暂时停用，请改用「停用」。',
    danger: true,
  })
  if (!ok) return
  try {
    await userApi.remove(record.id)
    feedback.success('用户已删除')
    await load()
  } catch {
    // 拦截器已提示（如「系统必须保留至少一名超级管理员」）
  }
}

// --------------------------------------------------------------------------- 导入

const importOpen = ref(false)
const importing = ref(false)
const importResult = ref<{
  created: number
  failed: Array<{ line: number; username: string; message: string }>
  default_password: string
} | null>(null)

function openImport(): void {
  importResult.value = null
  importOpen.value = true
}

/** 交给 Upload 的 beforeUpload：拦截自动上传，改由我们手动调接口。 */
async function handleFile(file: File): Promise<boolean> {
  importing.value = true
  try {
    importResult.value = await userApi.importCsv(file)
    if (importResult.value.created > 0) {
      await Promise.all([load(), org.loadDeptTree(true)])
    }
    feedback.success(`成功导入 ${importResult.value.created} 条`)
  } catch {
    // 拦截器已提示
  } finally {
    importing.value = false
  }
  return false
}

function downloadTemplate(): void {
  const csv =
    'username,real_name,email,phone,dept_code,position,roles,password\n' +
    'zhangsan,张三,zhangsan@example.com,13800000000,TECH,工程师,designer,\n' +
    'lisi,李四,,,FINANCE,会计,,\n'
  // 带 BOM，Excel 打开才不会中文乱码
  const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '用户导入模板.csv'
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="page-container">
    <a-card :bordered="false">
      <div class="page-toolbar">
        <a-space wrap>
          <a-input-search             v-model:value="query.keyword"
            placeholder="用户名 / 姓名 / 邮箱 / 手机号"
            style="width: 240px"
            allow-clear
            @search="search"
          />
          <a-tree-select
            v-model:value="query.dept_id"
            :tree-data="deptTreeData"
            :field-names="deptFieldNames"
            placeholder="所属部门"
            style="width: 190px"
            allow-clear
            tree-default-expand-all
          />
          <span class="inline-label">
            <a-switch v-model:checked="query.include_sub_depts" size="small" />
            含子部门
          </span>
          <a-select             v-model:value="query.status"
            :options="[
              { value: 'ACTIVE', label: '启用' },
              { value: 'DISABLED', label: '停用' },
            ]"
            placeholder="状态"
            style="width: 110px"
            allow-clear
          />
          <a-button type="primary" @click="search">查询</a-button>
          <a-button @click="resetQuery">
            <template #icon><ReloadOutlined /></template>
            重置
          </a-button>
        </a-space>

        <a-space>
          <a-button @click="openImport">
            <template #icon><UploadOutlined /></template>
            导入 CSV
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新建用户
          </a-button>
        </a-space>
      </div>

      <a-table         :columns="columns"
        :data-source="rows"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1400 }"
        :pagination="{
          current: paging.page,
          pageSize: paging.size,
          total: paging.total,
          showSizeChanger: true,
          showTotal: (total: number) => `共 ${total} 条`,
        }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'username'">
            <span class="text-mono">{{ record.username }}</span>
            <a-tag v-if="record.is_superuser" color="gold" style="margin-left: 6px">超管</a-tag>
          </template>

          <template v-else-if="column.key === 'dept_name'">
            <span v-if="record.dept_name">{{ record.dept_name }}</span>
            <span v-else class="text-muted">未分配</span>
          </template>

          <template v-else-if="column.key === 'position'">
            {{ record.position || '—' }}
          </template>

          <template v-else-if="column.key === 'roles'">
            <template v-if="record.roles.length">
              <a-tag v-for="role in record.roles" :key="role.id" color="blue">
                {{ role.name }}
              </a-tag>
            </template>
            <span v-else class="text-muted">—</span>
          </template>

          <template v-else-if="column.key === 'contact'">
            <div>{{ record.email || '—' }}</div>
            <div class="text-muted" style="font-size: 12px">{{ record.phone || '' }}</div>
          </template>

          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">
              {{ record.status === 'ACTIVE' ? '启用' : '停用' }}
            </a-tag>
          </template>

          <template v-else-if="column.key === 'last_login_at'">
            {{ formatDateTime(record.last_login_at) }}
          </template>

          <template v-else-if="column.key === 'action'">
            <a-space :size="4">
              <a-button type="link" size="small" @click="openEdit(record as UserItem)">
                <template #icon><EditOutlined /></template>
                编辑
              </a-button>
              <a-button type="link" size="small" @click="openResetPassword(record as UserItem)">
                <template #icon><KeyOutlined /></template>
                重置密码
              </a-button>
              <a-button                 type="link"
                size="small"
                :loading="togglingId === record.id"
                @click="toggleStatus(record as UserItem)"
              >
                {{ record.status === 'ACTIVE' ? '停用' : '启用' }}
              </a-button>
              <a-button type="link" size="small" danger @click="removeUser(record as UserItem)">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 新建 / 编辑 -->
    <a-modal
      v-model:open="editorOpen"
      :title="isCreate ? '新建用户' : '编辑用户'"
      :confirm-loading="editorSaving"
      :width="560"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitEditor"
    >
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item
              label="用户名"
              required
              :validate-status="formErrors.username ? 'error' : undefined"
              :help="formErrors.username"
            >
              <a-input                 v-model:value="form.username"
                :disabled="!isCreate"
                placeholder="登录账号，创建后不可修改"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item
              label="姓名"
              required
              :validate-status="formErrors.real_name ? 'error' : undefined"
              :help="formErrors.real_name"
            >
              <a-input v-model:value="form.real_name" placeholder="真实姓名" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item
          v-if="isCreate"
          label="初始密码"
          required
          :validate-status="formErrors.password ? 'error' : undefined"
          :help="formErrors.password"
        >
          <a-input v-model:value="form.password" placeholder="至少 6 位" />
          <template #extra>
            <span class="text-muted">建议让用户首次登录后自行修改</span>
          </template>
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item
              label="邮箱"
              :validate-status="formErrors.email ? 'error' : undefined"
              :help="formErrors.email"
            >
              <a-input v-model:value="form.email" placeholder="选填" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="手机号">
              <a-input v-model:value="form.phone" placeholder="选填" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="所属部门">
              <a-tree-select
                v-model:value="form.dept_id"
                :tree-data="deptTreeData"
                :field-names="deptFieldNames"
                placeholder="选择部门"
                allow-clear
                tree-default-expand-all
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="职位">
              <a-input v-model:value="form.position" placeholder="选填" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="角色" :validate-status="formErrors.role_ids ? 'error' : undefined" :help="formErrors.role_ids">
          <a-select             v-model:value="form.role_ids"
            mode="multiple"
            :options="roleOptions"
            placeholder="可多选；角色决定审批人解析与发起范围"
            allow-clear
            show-search
            option-filter-prop="label"
          />
        </a-form-item>

        <a-form-item label="状态">
          <a-radio-group v-model:value="form.status">
            <a-radio value="ACTIVE">启用</a-radio>
            <a-radio value="DISABLED">停用</a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 重置密码 -->
    <a-modal
      v-model:open="passwordOpen"
      title="重置密码"
      :confirm-loading="passwordSaving"
      ok-text="确认重置"
      cancel-text="取消"
      @ok="submitResetPassword"
    >
      <p>
        将为用户「<strong>{{ passwordTarget?.real_name }}</strong>」设置新密码。
        重置后该用户的所有已登录会话会立即失效。
      </p>
      <a-form-item
        label="新密码"
        :validate-status="passwordError ? 'error' : undefined"
        :help="passwordError"
      >
        <a-input v-model:value="passwordValue" placeholder="至少 6 位" />
      </a-form-item>
    </a-modal>

    <!-- 导入 CSV -->
    <a-modal v-model:open="importOpen" title="批量导入用户" :footer="null" :width="640">
      <a-alert
        type="info"
        show-icon
        message="CSV 需为 UTF-8 编码，必需列为 username、real_name"
        description="可选列：email、phone、dept_code（部门编码）、position、roles（角色标识，逗号分隔）、password（留空则用默认密码）"
        style="margin-bottom: 16px"
      />

      <a-space style="margin-bottom: 16px">
        <a-upload           :before-upload="handleFile"
          :show-upload-list="false"
          accept=".csv,text/csv"
          :disabled="importing"
        >
          <a-button type="primary" :loading="importing">
            <template #icon><UploadOutlined /></template>
            选择 CSV 文件
          </a-button>
        </a-upload>
        <a-button @click="downloadTemplate">
          <template #icon><DownloadOutlined /></template>
          下载模板
        </a-button>
      </a-space>

      <template v-if="importResult">
        <a-alert
          :type="importResult.failed.length ? 'warning' : 'success'"
          show-icon
          :message="`成功导入 ${importResult.created} 条，失败 ${importResult.failed.length} 条`"
          :description="`未提供密码的行使用默认密码：${importResult.default_password}`"
          style="margin-bottom: 12px"
        />
        <a-table           v-if="importResult.failed.length"
          :columns="[
            { title: '行号', dataIndex: 'line', width: 80 },
            { title: '用户名', dataIndex: 'username', width: 140 },
            { title: '失败原因', dataIndex: 'message' },
          ]"
          :data-source="importResult.failed"
          size="small"
          :pagination="false"
          row-key="line"
        />
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.inline-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}
</style>

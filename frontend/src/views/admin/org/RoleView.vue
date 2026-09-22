<script setup lang="ts">
import { DeleteOutlined, EditOutlined, PlusOutlined, TeamOutlined } from '@ant-design/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError } from '@/api/http'
import { roleApi } from '@/api/modules/role'
import UserSelect from '@/components/common/UserSelect.vue'
import type { DeptMember, Role } from '@/types/org'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'


const rows = ref<Role[]>([])
const loading = ref(false)
const keyword = ref('')

const columns = [
  { title: '角色标识', dataIndex: 'code', key: 'code', width: 170 },
  { title: '角色名称', dataIndex: 'name', key: 'name', width: 150 },
  { title: '说明', dataIndex: 'description', key: 'description' },
  { title: '成员数', key: 'member_count', width: 90 },
  { title: '来源', key: 'origin', width: 90 },
  { title: '状态', key: 'status', width: 80 },
  { title: '创建时间', key: 'created_at', width: 150 },
  { title: '操作', key: 'action', width: 220, fixed: 'right' as const },
]

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter(
    (r) => r.name.toLowerCase().includes(k) || r.code.toLowerCase().includes(k),
  )
})

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await roleApi.list()
  } finally {
    loading.value = false
  }
}

onMounted(load)

// --------------------------------------------------------------------------- 新建 / 编辑

const editorOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const isCreate = computed(() => editingId.value === null)
const form = reactive({ code: '', name: '', description: '', status: 'ACTIVE' })
const formErrors = reactive<Record<string, string>>({})

function openCreate(): void {
  editingId.value = null
  Object.assign(form, { code: '', name: '', description: '', status: 'ACTIVE' })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  editorOpen.value = true
}

function openEdit(record: Role): void {
  editingId.value = record.id
  Object.assign(form, {
    code: record.code,
    name: record.name,
    description: record.description ?? '',
    status: record.status,
  })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  editorOpen.value = true
}

async function submitEditor(): Promise<void> {
  Object.keys(formErrors).forEach((k) => delete formErrors[k])

  if (isCreate.value) {
    if (!form.code) formErrors.code = '请输入角色标识'
    else if (!/^[a-z][a-z0-9_]*$/.test(form.code)) {
      formErrors.code = '需以小写字母开头，仅含小写字母、数字、下划线'
    }
  }
  if (!form.name) formErrors.name = '请输入角色名称'
  if (Object.keys(formErrors).length) return

  saving.value = true
  try {
    if (isCreate.value) {
      await roleApi.create({
        code: form.code,
        name: form.name,
        description: form.description || null,
      })
      feedback.success('角色已创建')
    } else {
      await roleApi.update(editingId.value as number, {
        name: form.name,
        description: form.description || null,
        status: form.status as 'ACTIVE' | 'DISABLED',
      })
      feedback.success('角色已更新')
    }
    editorOpen.value = false
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.code === 'ROLE_CODE_EXISTS') {
      formErrors.code = error.message
    }
  } finally {
    saving.value = false
  }
}

async function removeRole(record: Role): Promise<void> {
  const ok = await feedback.confirm({
    title: `确定删除角色「${record.name}」吗？`,
    content: '只有没有成员的角色才能删除；内置角色不可删除。',
    danger: true,
  })
  if (!ok) return
  try {
    await roleApi.remove(record.id)
    feedback.success('角色已删除')
    await load()
  } catch {
    // 拦截器已提示（ROLE_BUILTIN_PROTECTED / ROLE_HAS_MEMBERS）
  }
}

// --------------------------------------------------------------------------- 成员

const memberOpen = ref(false)
const memberSaving = ref(false)
const memberLoading = ref(false)
const memberTarget = ref<Role | null>(null)
const memberIds = ref<number[]>([])
/** 当前角色的完整成员列表，用于表格展示 */
const memberList = ref<DeptMember[]>([])
/** 喂给 UserSelect 的「已知人员」，保证未出现在搜索结果里的成员也有正确标签 */
const memberSeed = computed(() =>
  memberList.value.map((m) => ({ id: m.id, username: m.username, real_name: m.real_name })),
)
const memberRows = computed(() => memberList.value.filter((m) => memberIds.value.includes(m.id)))

const memberColumns = [
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '姓名', dataIndex: 'real_name', key: 'real_name' },
  { title: '职位', dataIndex: 'position', key: 'position' },
  { title: '状态', key: 'status', width: 90 },
]

async function openMembers(record: Role): Promise<void> {
  memberTarget.value = record
  memberOpen.value = true
  memberLoading.value = true
  try {
    memberList.value = await roleApi.members(record.id)
    memberIds.value = memberList.value.map((m) => m.id)
  } finally {
    memberLoading.value = false
  }
}

async function submitMembers(): Promise<void> {
  if (!memberTarget.value) return
  memberSaving.value = true
  try {
    await roleApi.setMembers(memberTarget.value.id, memberIds.value)
    memberOpen.value = false
    feedback.success('成员已更新')
    await load()
  } finally {
    memberSaving.value = false
  }
}

async function removeMember(userId: number): Promise<void> {
  if (!memberTarget.value) return
  memberIds.value = memberIds.value.filter((id) => id !== userId)
  await roleApi.setMembers(memberTarget.value.id, memberIds.value)
  await load()
}
</script>

<template>
  <div class="page-container">
    <a-card :bordered="false">
      <div class="page-toolbar">
        <a-input-search           v-model:value="keyword"
          placeholder="搜索角色名称或标识"
          allow-clear
          style="width: 240px"
        />
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建角色
        </a-button>
      </div>

      <a-alert
        type="info"
        show-icon
        message="角色用于审批人解析与发起范围控制（PRD §2）"
        description="内置角色的标识被流程定义直接引用，因此不可删除、不可停用；自定义角色可以自由维护。"
        style="margin-bottom: 16px"
      />

      <a-table         :columns="columns"
        :data-source="filtered"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1100 }"
        :pagination="{ pageSize: 20, showTotal: (total: number) => `共 ${total} 条` }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'code'">
            <span class="text-mono">{{ record.code }}</span>
          </template>

          <template v-else-if="column.key === 'description'">
            {{ record.description || '—' }}
          </template>

          <template v-else-if="column.key === 'member_count'">
            <a @click="openMembers(record as Role)">{{ record.member_count }} 人</a>
          </template>

          <template v-else-if="column.key === 'origin'">
            <a-tag :color="record.is_builtin ? 'gold' : 'default'">
              {{ record.is_builtin ? '内置' : '自定义' }}
            </a-tag>
          </template>

          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">
              {{ record.status === 'ACTIVE' ? '启用' : '停用' }}
            </a-tag>
          </template>

          <template v-else-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>

          <template v-else-if="column.key === 'action'">
            <a-space :size="4">
              <a-button type="link" size="small" @click="openMembers(record as Role)">
                <template #icon><TeamOutlined /></template>
                成员
              </a-button>
              <a-button type="link" size="small" @click="openEdit(record as Role)">
                <template #icon><EditOutlined /></template>
                编辑
              </a-button>
              <a-button                 type="link"
                size="small"
                danger
                :disabled="record.is_builtin"
                @click="removeRole(record as Role)"
              >
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="editorOpen"
      :title="isCreate ? '新建角色' : '编辑角色'"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitEditor"
    >
      <a-form layout="vertical">
        <a-form-item
          label="角色标识"
          :required="isCreate"
          :validate-status="formErrors.code ? 'error' : undefined"
          :help="formErrors.code || (isCreate ? '用于流程定义中引用，创建后不可修改' : '创建后不可修改')"
        >
          <a-input             v-model:value="form.code"
            :disabled="!isCreate"
            placeholder="小写字母开头，如 finance_manager"
          />
        </a-form-item>
        <a-form-item
          label="角色名称"
          required
          :validate-status="formErrors.name ? 'error' : undefined"
          :help="formErrors.name"
        >
          <a-input v-model:value="form.name" placeholder="如：财务经理" />
        </a-form-item>
        <a-form-item label="说明">
          <a-textarea v-model:value="form.description" :rows="2" placeholder="选填" />
        </a-form-item>
        <a-form-item v-if="!isCreate" label="状态">
          <a-radio-group v-model:value="form.status" :disabled="rows.find((r) => r.id === editingId)?.is_builtin">
            <a-radio value="ACTIVE">启用</a-radio>
            <a-radio value="DISABLED">停用</a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="memberOpen"
      :title="`「${memberTarget?.name ?? ''}」的成员`"
      :confirm-loading="memberSaving"
      ok-text="保存"
      cancel-text="取消"
      :width="620"
      @ok="submitMembers"
    >
      <a-spin :spinning="memberLoading">
        <a-alert
          type="info"
          show-icon
          message="覆盖式保存：不在下方列表中的原成员会被移出该角色。"
          style="margin-bottom: 16px"
        />
        <UserSelect
          v-model="memberIds"
          multiple
          :seed="memberSeed"
          placeholder="搜索并选择成员"
          style="margin-bottom: 16px"
        />

        <a-table           :columns="memberColumns"
          :data-source="memberRows"
          row-key="id"
          size="small"
          :pagination="false"
          :locale="{ emptyText: '该角色暂无成员' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'position'">
              {{ record.position || '—' }}
            </template>
            <template v-else-if="column.key === 'status'">
              {{ record.status || '—' }}
            </template>
            <template v-else-if="column.key === 'username'">
              <a-space>
                <span class="text-mono">{{ record.username }}</span>
                <a-button type="link" size="small" danger @click="removeMember((record as DeptMember).id)">
                  移除
                </a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-spin>
    </a-modal>
  </div>
</template>

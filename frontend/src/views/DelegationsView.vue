<script setup lang="ts">
import { PlusOutlined } from '@ant-design/icons-vue'
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
} from 'ant-design-vue'
import dayjs, { type Dayjs } from 'dayjs'
import { computed, onMounted, reactive, ref } from 'vue'

import { delegationApi } from '@/api/modules/delegation'
import { flowApi } from '@/api/modules/flow'
import { userApi } from '@/api/modules/user'
import { useAuthStore } from '@/stores/auth'
import type { Delegation } from '@/types/delegation'
import type { FlowTemplate } from '@/types/flow'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const auth = useAuthStore()

const rows = ref<Delegation[]>([])
const flows = ref<FlowTemplate[]>([])
const users = ref<Array<{ value: number; label: string }>>([])
const loading = ref(false)
const allUsers = ref(false)

const editorOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const isCreate = computed(() => editingId.value === null)

const form = reactive({
  delegateeId: undefined as number | undefined,
  range: undefined as [Dayjs, Dayjs] | undefined,
  flowIds: [] as number[],
  reason: '',
})

const flowOptions = computed(() => flows.value.map((flow) => ({ value: flow.id, label: flow.name })))
const userOptions = computed(() => users.value)

/** 后端时间是 naive UTC；编辑时要按 UTC 解析，否则会整体偏移 8 小时。 */
function fromUtc(value: string): Dayjs {
  const iso = /Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
  return dayjs(new Date(iso))
}

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await delegationApi.list(allUsers.value)
  } finally {
    loading.value = false
  }
}

async function loadOptions(): Promise<void> {
  // 流程模板列表需要设计者权限；普通用户创建委托时不应因此连人员选项都加载失败。
  const flowListPromise = auth.isDesigner
    ? flowApi.listTemplates().catch(() => [] as FlowTemplate[])
    : Promise.resolve([] as FlowTemplate[])
  const [flowList, userList] = await Promise.all([
    flowListPromise,
    userApi.options({ limit: 200 }),
  ])
  flows.value = flowList
  users.value = userList.map((user) => ({
    value: user.id,
    label: `${user.real_name}${user.dept_name ? `（${user.dept_name}）` : ''}`,
  }))
}

function openCreate(): void {
  editingId.value = null
  form.delegateeId = undefined
  form.range = undefined
  form.flowIds = []
  form.reason = ''
  void loadOptions()
  editorOpen.value = true
}

function openEdit(record: Delegation): void {
  editingId.value = record.id
  form.delegateeId = record.delegatee_id
  form.range = [fromUtc(record.start_at), fromUtc(record.end_at)]
  form.flowIds = record.flow_template_ids ?? []
  form.reason = record.reason
  void loadOptions()
  editorOpen.value = true
}

async function submit(): Promise<void> {
  if (!form.delegateeId) {
    feedback.error('请选择被委托人')
    return
  }
  if (!form.range) {
    feedback.error('请选择委托时段')
    return
  }
  if (!form.reason.trim()) {
    feedback.error('请填写委托原因')
    return
  }
  const payload = {
    delegatee_id: form.delegateeId,
    start_at: form.range[0].toISOString(),
    end_at: form.range[1].toISOString(),
    flow_template_ids: form.flowIds.length ? form.flowIds : null,
    reason: form.reason.trim(),
  }
  saving.value = true
  try {
    if (isCreate.value) {
      await delegationApi.create(payload)
      feedback.success('委托已创建')
    } else {
      await delegationApi.update(editingId.value as number, payload)
      feedback.success('已保存')
    }
    editorOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function cancel(record: Delegation): Promise<void> {
  const ok = await feedback.confirm({
    title: '取消该委托？',
    content: '取消后新任务不再转给被委托人，已派出的待办不受影响。',
    danger: true,
  })
  if (!ok) return
  await delegationApi.cancel(record.id)
  feedback.success('已取消')
  await load()
}

async function onAllUsersChange(): Promise<void> {
  await load()
}

const columns = [
  { title: '委托人', key: 'delegator_name', dataIndex: 'delegator_name', width: 140 },
  { title: '被委托人', key: 'delegatee_name', dataIndex: 'delegatee_name', width: 140 },
  { title: '生效时段', key: 'range', width: 260 },
  { title: '适用流程', key: 'flows', width: 200 },
  { title: '原因', key: 'reason', dataIndex: 'reason' },
  { title: '状态', key: 'status', width: 90 },
  { title: '操作', key: 'action', width: 150 },
]

function flowNames(record: Delegation): string {
  if (!record.flow_template_ids?.length) return '全部流程'
  return record.flow_template_ids
    .map((id) => flows.value.find((flow) => flow.id === id)?.name ?? `#${id}`)
    .join('、')
}

onMounted(() => {
  void load()
  void loadOptions()
})
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <template #title>委托管理</template>
      <template #extra>
        <Space>
          <span v-if="auth.isAdmin" class="text-muted admin-switch">
            <Switch v-model:checked="allUsers" size="small" @change="onAllUsersChange" />
            查看全部
          </span>
          <Button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新建委托
          </Button>
        </Space>
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
          <template v-if="column.key === 'range'">
            {{ formatDateTime(record.start_at) }} 至 {{ formatDateTime(record.end_at) }}
          </template>
          <template v-else-if="column.key === 'flows'">
            {{ flowNames(record as Delegation) }}
          </template>
          <template v-else-if="column.key === 'status'">
            <Tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">
              {{ record.status === 'ACTIVE' ? '生效中' : '已取消' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space :size="2">
              <Button
                v-if="record.status === 'ACTIVE'"
                type="link"
                size="small"
                @click="openEdit(record as Delegation)"
              >
                编辑
              </Button>
              <Button
                v-if="record.status === 'ACTIVE'"
                type="link"
                size="small"
                danger
                @click="cancel(record as Delegation)"
              >
                取消
              </Button>
            </Space>
          </template>
        </template>
      </Table>
      <Empty v-else description="还没有委托" />
    </Card>

    <Modal
      v-model:open="editorOpen"
      :title="isCreate ? '新建委托' : '编辑委托'"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      width="620px"
      @ok="submit"
    >
      <div class="form-row">
        <span class="label">被委托人</span>
        <Select
          v-model:value="form.delegateeId"
          :options="userOptions"
          show-search
          option-filter-prop="label"
          placeholder="选择人员"
          class="control"
        />
      </div>
      <div class="form-row">
        <span class="label">生效时段</span>
        <DatePicker.RangePicker
          v-model:value="form.range"
          show-time
          format="YYYY-MM-DD HH:mm"
          class="control"
        />
      </div>
      <div class="form-row">
        <span class="label">适用流程</span>
        <Select
          v-model:value="form.flowIds"
          mode="multiple"
          :options="flowOptions"
          placeholder="不选则全部流程"
          class="control"
        />
      </div>
      <div class="form-row">
        <span class="label">原因</span>
        <Input v-model:value="form.reason" placeholder="必填，如：出差 / 休假" class="control" />
      </div>
      <div class="text-muted hint">委托只影响生效期内新派发的任务，已有待办需要手动转办。</div>
    </Modal>
  </div>
</template>

<style scoped lang="scss">
.admin-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.label {
  flex: 0 0 68px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.control {
  flex: 1;
}

.hint {
  margin-top: 4px;
  font-size: 12px;
}
</style>

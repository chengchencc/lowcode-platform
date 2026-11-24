<script setup lang="ts">
/**
 * 流程实例管理（PRD F8.1 / §5「审批管理 → 实例管理」）。
 *
 * 管理员视角的**全组织审批实例**：运行中 + 全部办结状态，按最后活动时间倒序，
 * 方便盯住最近还在流转的单据。草稿是自动暂存的未提交数据，不在这里。
 *
 * 与「归档台账」的分工：
 *   - 实例管理：运行中也要看，关心「最近动过哪些单子」；
 *   - 归档台账：只看办结单据，支持导出 CSV。
 *
 * 这里严格限管理员（后端也会拦）。
 */
import { ReloadOutlined } from '@ant-design/icons-vue'
import { Button, Card, DatePicker, Input, Select, Space, Table, Tag } from 'ant-design-vue'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { flowApi } from '@/api/modules/flow'
import { instanceApi } from '@/api/modules/instance'
import type { ManageQuery } from '@/api/modules/instance'
import InstanceFilterBuilder from '@/components/instance/InstanceFilterBuilder.vue'
import type { FlowTemplate } from '@/types/flow'
import type { InstanceItem } from '@/types/instance'
import { INSTANCE_STATUS_META } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()

const rows = ref<InstanceItem[]>([])
const flows = ref<FlowTemplate[]>([])
const loading = ref(false)
const filters = ref('')

const query = reactive({
  keyword: '',
  status: '',
  flow_template_id: undefined as number | undefined,
  range: undefined as [string, string] | undefined,
})
const paging = reactive({ page: 1, size: 20, total: 0 })

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'RUNNING', label: '审批中' },
  { value: 'APPROVED', label: '已通过' },
  { value: 'REJECTED', label: '已驳回' },
  { value: 'WITHDRAWN', label: '已撤回' },
  { value: 'TERMINATED', label: '已终止' },
]

const columns = [
  { title: '实例单号', key: 'code', width: 165 },
  { title: '标题', key: 'title', width: 220 },
  { title: '流程', key: 'flow_template_name', width: 140 },
  { title: '发起人', key: 'initiator_name', width: 110 },
  { title: '发起部门', key: 'initiator_dept_name', width: 120 },
  { title: '轮次', key: 'round', width: 70 },
  { title: '最后活动', key: 'last_action_at', width: 150 },
  { title: '状态', key: 'status', width: 110 },
  { title: '待办', key: 'pending_count', width: 70 },
  { title: '操作', key: 'action', width: 90, fixed: 'right' as const },
]

function params(): ManageQuery {
  return {
    keyword: query.keyword || undefined,
    status: query.status || undefined,
    flow_template_id: query.flow_template_id,
    active_from: query.range?.[0] || undefined,
    active_to: query.range?.[1] || undefined,
    filters: filters.value || undefined,
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await instanceApi.manage({
      ...params(),
      page: paging.page,
      size: paging.size,
    })
    rows.value = data.items
    paging.total = data.total
  } finally {
    loading.value = false
  }
}

async function loadFlows(): Promise<void> {
  flows.value = await flowApi.listTemplates()
}

onMounted(() => {
  void load()
  void loadFlows()
})

function search(): void {
  paging.page = 1
  void load()
}

function onFiltersChange(value: string): void {
  filters.value = value
  search()
}

function onTableChange(pagination: { current?: number; pageSize?: number }): void {
  paging.page = pagination.current ?? 1
  paging.size = pagination.pageSize ?? 20
  void load()
}

function open(row: InstanceItem): void {
  void router.push({ name: 'instance-detail', params: { id: row.id } })
}

function statusMeta(status: string) {
  return INSTANCE_STATUS_META[status as keyof typeof INSTANCE_STATUS_META]
}
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <div class="page-toolbar">
        <Space wrap>
          <Input
            v-model:value="query.keyword"
            placeholder="标题 / 实例单号"
            allow-clear
            style="width: 200px"
            @press-enter="search"
          />
          <Select
            v-model:value="query.status"
            :options="STATUS_OPTIONS"
            style="width: 160px"
            @change="search"
          />
          <Select
            v-model:value="query.flow_template_id"
            :options="flows.map((f) => ({ value: f.id, label: f.name }))"
            placeholder="全部流程"
            style="width: 180px"
            allow-clear
            show-search
            option-filter-prop="label"
            @change="search"
          />
          <DatePicker.RangePicker
            v-model:value="query.range"
            value-format="YYYY-MM-DD"
            :placeholder="['最后活动起', '最后活动止']"
            @change="search"
          />
          <Button @click="search">
            <template #icon><ReloadOutlined /></template>
            查询
          </Button>
        </Space>
      </div>

      <InstanceFilterBuilder
        :flow-template-id="query.flow_template_id"
        scope="manage"
        :model-value="filters"
        @update:model-value="onFiltersChange"
      />

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1300 }"
        :pagination="{
          current: paging.page, pageSize: paging.size, total: paging.total,
          showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
        }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <a @click="open(record as InstanceItem)">{{ record.title }}</a>
          </template>
          <template v-else-if="column.key === 'code'">
            <span class="text-mono text-muted">{{ record.code }}</span>
          </template>
          <template v-else-if="column.key === 'round'">
            <Tag v-if="record.round > 1" color="purple">第 {{ record.round }} 轮</Tag>
            <span v-else class="text-muted">1</span>
          </template>
          <template v-else-if="column.key === 'last_action_at'">
            {{ record.last_action_at ? formatDateTime(record.last_action_at) : '—' }}
          </template>
          <template v-else-if="column.key === 'status'">
            <Tag :color="statusMeta(record.status)?.color">
              {{ statusMeta(record.status)?.text ?? record.status }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'pending_count'">
            <span :class="{ 'text-muted': !record.pending_count }">
              {{ record.pending_count ?? 0 }}
            </span>
          </template>
          <template v-else-if="column.key === 'action'">
            <Button type="link" size="small" @click="open(record as InstanceItem)">
              查看
            </Button>
          </template>
        </template>
      </Table>
    </Card>
  </div>
</template>

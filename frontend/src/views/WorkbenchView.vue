<script setup lang="ts">
/**
 * 工作台（PRD §5）：待办 / 已办 / 我发起的 / 抄送给我。
 *
 * 四类列表共用一套列定义与分页，用 `type` 区分数据源 ——
 * 否则会出现「四个页面各写一遍表格，改一处要改四处」。
 *
 * 会签组的待办会带 `group_member_count`，列表里用标签提示「同组还有 N 条」
 * （PRD F4.1「会签组待办合并展示、分别操作」）。
 */
import { EyeOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { Button, Card, Input, Select, Space, Table, Tag } from 'ant-design-vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { instanceApi, taskApi } from '@/api/modules/instance'
import InstanceFilterBuilder from '@/components/instance/InstanceFilterBuilder.vue'
import type { FlowTemplate } from '@/types/flow'
import type { InstanceItem, TaskRow } from '@/types/instance'
import { INSTANCE_STATUS_META } from '@/types/instance'
import { formatDateTime, formatRelative } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const route = useRoute()
const router = useRouter()

type TabKey = 'todo' | 'done' | 'cc' | 'mine'

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'todo', label: '待办' },
  { key: 'done', label: '已办' },
  { key: 'mine', label: '我发起的' },
  { key: 'cc', label: '抄送给我' },
]

const activeTab = ref<TabKey>((route.params.type as TabKey) || 'todo')
const taskRows = ref<TaskRow[]>([])
const instanceRows = ref<InstanceItem[]>([])
const loading = ref(false)
const query = reactive({ keyword: '', unread_only: false })
const paging = reactive({ page: 1, size: 20, total: 0 })
const mineFlows = ref<FlowTemplate[]>([])
const mineFlowId = ref<number | undefined>(undefined)
const mineFilters = ref('')

const isTaskList = computed(() => activeTab.value !== 'mine')

const taskColumns = computed(() => {
  const cols = [
    { title: '标题', key: 'title', width: 260 },
    { title: '流程', key: 'flow_template_name', width: 150 },
    { title: '当前节点', key: 'node_name', width: 150 },
    { title: '发起人', key: 'initiator_name', width: 110 },
    {
      title: activeTab.value === 'done' ? '处理时间' : '到达时间',
      key: 'time',
      width: 150,
    },
    { title: '状态', key: 'status', width: 110 },
    { title: '操作', key: 'action', width: 90, fixed: 'right' as const },
  ]
  return cols
})

const instanceColumns = [
  { title: '标题', key: 'title', width: 260 },
  { title: '编号', key: 'code', width: 160 },
  { title: '流程', key: 'flow_template_name', width: 150 },
  { title: '当前节点', key: 'current_node_keys', width: 170 },
  { title: '提交时间', key: 'started_at', width: 130 },
  { title: '状态', key: 'status', width: 120 },
  { title: '操作', key: 'action', width: 90, fixed: 'right' as const },
]

async function load(): Promise<void> {
  loading.value = true
  try {
    const params = {
      page: paging.page,
      size: paging.size,
      keyword: query.keyword || undefined,
      ...(activeTab.value === 'mine'
        ? {
            flow_template_id: mineFlowId.value,
            filters: mineFilters.value || undefined,
          }
        : {}),
    }
    if (activeTab.value === 'mine') {
      const data = await taskApi.mine(params)
      instanceRows.value = data.items
      paging.total = data.total
    } else if (activeTab.value === 'todo') {
      const data = await taskApi.todo(params)
      taskRows.value = data.items
      paging.total = data.total
    } else if (activeTab.value === 'done') {
      const data = await taskApi.done(params)
      taskRows.value = data.items
      paging.total = data.total
    } else {
      const data = await taskApi.cc({ ...params, unread_only: query.unread_only })
      taskRows.value = data.items
      paging.total = data.total
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  void instanceApi.myFlowTemplates().then((flows) => {
    mineFlows.value = flows
  })
})

watch(activeTab, (next) => {
  paging.page = 1
  void router.replace({ name: 'workbench', params: { type: next } })
  void load()
})

watch(
  () => route.params.type,
  (next) => {
    if (next && next !== activeTab.value) activeTab.value = next as TabKey
  },
)

function search(): void {
  paging.page = 1
  void load()
}

function onMineFlowChange(): void {
  mineFilters.value = ''
  search()
}

function onMineFiltersChange(value: string): void {
  mineFilters.value = value
  search()
}

function onTableChange(pagination: { current?: number; pageSize?: number }): void {
  paging.page = pagination.current ?? 1
  paging.size = pagination.pageSize ?? 20
  void load()
}

/** 打开详情：待办要带上 assignment，让详情页知道「以哪个待办的身份看」 */
function openTask(row: TaskRow): void {
  void router.push({
    name: 'instance-detail',
    params: { id: row.instance_id },
    query: { assignment: row.assignment_id },
  })
}

function openInstance(row: InstanceItem): void {
  void router.push({ name: 'instance-detail', params: { id: row.id } })
}

async function markRead(row: TaskRow): Promise<void> {
  await taskApi.markRead(row.assignment_id)
  feedback.success('已标记为已读')
  await load()
}

function statusMeta(status?: string | null) {
  return INSTANCE_STATUS_META[(status ?? 'DRAFT') as keyof typeof INSTANCE_STATUS_META]
}
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <a-tabs v-model:active-key="activeTab">
        <a-tab-pane v-for="tab in TABS" :key="tab.key" :tab="tab.label" />
      </a-tabs>

      <div v-if="activeTab === 'mine'" class="page-toolbar">
        <Select
          v-model:value="mineFlowId"
          :options="mineFlows.map((flow) => ({ value: flow.id, label: flow.name }))"
          placeholder="全部流程"
          style="width: 220px"
          allow-clear
          show-search
          option-filter-prop="label"
          @change="onMineFlowChange"
        />
      </div>

      <div class="page-toolbar">
        <Space>
          <Input.Search
            v-model:value="query.keyword"
            placeholder="标题或编号"
            style="width: 220px"
            allow-clear
            @search="search"
          />
          <a-checkbox
            v-if="activeTab === 'cc'"
            v-model:checked="query.unread_only"
            @change="search"
          >
            只看未读
          </a-checkbox>
        </Space>
        <Button @click="load">
          <template #icon><ReloadOutlined /></template>
          刷新
        </Button>
      </div>

      <InstanceFilterBuilder
        v-if="activeTab === 'mine'"
        :flow-template-id="mineFlowId"
        scope="mine"
        :model-value="mineFilters"
        @update:model-value="onMineFiltersChange"
      />

      <!-- ------------------------------------------------ 任务列表 -->
      <Table
        v-if="isTaskList"
        :columns="taskColumns"
        :data-source="taskRows"
        :loading="loading"
        row-key="assignment_id"
        size="middle"
        :scroll="{ x: 1100 }"
        :pagination="{
          current: paging.page, pageSize: paging.size, total: paging.total,
          showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
        }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <a @click="openTask(record as TaskRow)">{{ record.instance_title }}</a>
            <div class="text-muted tiny">{{ record.instance_code }}</div>
          </template>

          <template v-else-if="column.key === 'node_name'">
            <Tag>{{ record.node_type === 'CC' ? '抄送' : '' }}{{ record.node_name }}</Tag>
            <Tag v-if="(record.group_member_count ?? 0) > 1" color="purple" class="group-tag">
              同组 {{ record.group_member_count }} 条
            </Tag>
          </template>

          <template v-else-if="column.key === 'flow_template_name'">
            {{ record.flow_template_name || '—' }}
          </template>

          <template v-else-if="column.key === 'initiator_name'">
            {{ record.initiator_name || '—' }}
          </template>

          <template v-else-if="column.key === 'time'">
            <span v-if="activeTab === 'done'">{{ formatDateTime(record.acted_at) }}</span>
            <span v-else>{{ formatRelative(record.activated_at) }}</span>
          </template>

          <template v-else-if="column.key === 'status'">
            <Tag :color="statusMeta(record.instance_status)?.color">
              {{ statusMeta(record.instance_status)?.text }}
            </Tag>
            <Tag v-if="activeTab === 'done' && record.result" class="result-tag">
              {{ record.result === 'AGREE' ? '同意'
                : record.result === 'REJECT' ? '驳回'
                : record.result === 'RETURN' ? '退回'
                : record.result === 'SUBMIT' ? '提交' : record.result }}
            </Tag>
            <Tag v-if="activeTab === 'cc' && !record.is_read" color="red">未读</Tag>
          </template>

          <template v-else-if="column.key === 'action'">
            <Space :size="2">
              <Button type="link" size="small" @click="openTask(record as TaskRow)">
                <template #icon><EyeOutlined /></template>
                {{ activeTab === 'todo' ? '处理' : '查看' }}
              </Button>
              <Button
                v-if="activeTab === 'cc' && !record.is_read"
                type="link"
                size="small"
                @click="markRead(record as TaskRow)"
              >
                已读
              </Button>
            </Space>
          </template>
        </template>
      </Table>

      <!-- ------------------------------------------------ 我发起的 -->
      <Table
        v-else
        :columns="instanceColumns"
        :data-source="instanceRows"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1100 }"
        :pagination="{
          current: paging.page, pageSize: paging.size, total: paging.total,
          showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
        }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <a @click="openInstance(record as InstanceItem)">{{ record.title }}</a>
          </template>

          <template v-else-if="column.key === 'code'">
            <span class="text-mono tiny">{{ record.code }}</span>
          </template>

          <template v-else-if="column.key === 'current_node_keys'">
            <template v-if="record.current_node_keys?.length">
              <Tag v-for="name in record.current_node_keys" :key="name">{{ name }}</Tag>
            </template>
            <span v-else class="text-muted">—</span>
          </template>

          <template v-else-if="column.key === 'started_at'">
            {{ formatDateTime(record.started_at) }}
          </template>

          <template v-else-if="column.key === 'status'">
            <Tag :color="statusMeta(record.status)?.color">{{ statusMeta(record.status)?.text }}</Tag>
            <Tag v-if="record.round > 1" color="purple" class="result-tag">
              第 {{ record.round }} 轮
            </Tag>
          </template>

          <template v-else-if="column.key === 'action'">
            <Button type="link" size="small" @click="openInstance(record as InstanceItem)">
              <template #icon><EyeOutlined /></template>
              查看
            </Button>
          </template>
        </template>
      </Table>
    </Card>
  </div>
</template>

<style scoped>
.tiny {
  font-size: 11px;
}

.group-tag,
.result-tag {
  font-size: 10px;
  margin-left: 2px;
}
</style>

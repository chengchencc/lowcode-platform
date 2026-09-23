<script setup lang="ts">
/**
 * 实例管理 / 归档检索（PRD F8.1 / §5「审批管理 → 实例管理」）。
 *
 * 管理员视角的**全组织单据**：默认只看已归档（已通过），
 * 也可以放开到撤回/终止/驳回等终态去查历史。
 *
 * 与工作台的分工：工作台是「与我相关的」，这里是「全部的」——
 * 所以这里严格限管理员（后端也会拦）。
 *
 * 导出 CSV 走 `utils/download.ts`：后端只认 Bearer 头，
 * 直接给 `<a href>` 会拿到 401（这一点 M4 的附件链接就踩过）。
 * 列 = 字段标签（含运行中追加的动态字段），一行一张单子。
 */
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { Button, Card, DatePicker, Input, Select, Space, Table, Tag } from 'ant-design-vue'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { instanceApi } from '@/api/modules/instance'
import { flowApi } from '@/api/modules/flow'
import type { ArchiveQuery } from '@/api/modules/instance'
import type { FlowTemplate } from '@/types/flow'
import type { InstanceItem } from '@/types/instance'
import { INSTANCE_STATUS_META } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'
import { downloadFile } from '@/utils/download'
import { feedback } from '@/utils/feedback'

const router = useRouter()

const rows = ref<InstanceItem[]>([])
const flows = ref<FlowTemplate[]>([])
const loading = ref(false)
const exporting = ref(false)

const query = reactive({
  keyword: '',
  status: 'APPROVED',
  flow_template_id: undefined as number | undefined,
  range: undefined as [string, string] | undefined,
})
const paging = reactive({ page: 1, size: 20, total: 0 })

/** 终态选项 —— 归档表的意义就在于「事后翻得出来」 */
const STATUS_OPTIONS = [
  { value: 'APPROVED', label: '已通过' },
  { value: 'REJECTED', label: '已驳回' },
  { value: 'WITHDRAWN', label: '已撤回' },
  { value: 'TERMINATED', label: '已终止' },
  { value: 'APPROVED,REJECTED,WITHDRAWN,TERMINATED', label: '全部终态' },
]

const columns = [
  { title: '编号', key: 'code', width: 165 },
  { title: '标题', key: 'title', width: 220 },
  { title: '流程', key: 'flow_template_name', width: 140 },
  { title: '发起人', key: 'initiator_name', width: 110 },
  { title: '发起部门', key: 'initiator_dept_name', width: 120 },
  { title: '轮次', key: 'round', width: 70 },
  { title: '完成时间', key: 'finished_at', width: 150 },
  { title: '状态', key: 'status', width: 110 },
  { title: '操作', key: 'action', width: 90, fixed: 'right' as const },
]

function params(): ArchiveQuery {
  return {
    keyword: query.keyword || undefined,
    status: query.status || undefined,
    flow_template_id: query.flow_template_id,
    finished_from: query.range?.[0] || undefined,
    finished_to: query.range?.[1] || undefined,
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await instanceApi.archive({
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

function onTableChange(pagination: { current?: number; pageSize?: number }): void {
  paging.page = pagination.current ?? 1
  paging.size = pagination.pageSize ?? 20
  void load()
}

function open(row: InstanceItem): void {
  void router.push({ name: 'instance-detail', params: { id: row.id } })
}

async function exportCsv(): Promise<void> {
  exporting.value = true
  try {
    // 导出用**当前筛选条件**，但不受分页限制 —— 否则只能导出一页
    await downloadFile(instanceApi.archiveExportUrl(params()), 'flowform-archive.csv')
    feedback.success('已开始下载')
  } catch {
    // 拦截器已提示（权限 / 网络）
  } finally {
    exporting.value = false
  }
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
            placeholder="标题 / 编号"
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
            @change="search"
          />
          <Button @click="search">
            <template #icon><ReloadOutlined /></template>
            查询
          </Button>
        </Space>

        <Button type="primary" ghost :loading="exporting" @click="exportCsv">
          <template #icon><DownloadOutlined /></template>
          导出 CSV
        </Button>
      </div>

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1200 }"
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
          <template v-else-if="column.key === 'finished_at'">
            {{ record.finished_at ? formatDateTime(record.finished_at) : '—' }}
          </template>
          <template v-else-if="column.key === 'status'">
            <Tag :color="statusMeta(record.status)?.color">
              {{ statusMeta(record.status)?.text ?? record.status }}
            </Tag>
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

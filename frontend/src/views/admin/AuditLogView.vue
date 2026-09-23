<script setup lang="ts">
/**
 * 操作审计（F6.6）。
 *
 * 审计是**只增不改**的合规材料，用它的场景是「事后翻得到」：
 * 谁、什么时候、对什么做了什么。所以筛选按人的记忆方式来给 ——
 * 关键词同时匹配摘要与操作人（不要求先知道动作枚举），时间用区间选。
 *
 * 明细里存的是 JSON，展开看即可；导出的 CSV 是给合规留存的。
 */
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { Button, Card, DatePicker, Input, Select, Space, Table, Tag } from 'ant-design-vue'
import { onMounted, reactive, ref } from 'vue'

import { auditApi, type AuditLogItem, type AuditQuery } from '@/api/modules/role'
import { AUDIT_ACTION_LABELS, AUDIT_BIZ_LABELS } from '@/stores/app'
import { formatDateTime } from '@/utils/datetime'
import { downloadFile } from '@/utils/download'
import { feedback } from '@/utils/feedback'

const rows = ref<AuditLogItem[]>([])
const loading = ref(false)
const exporting = ref(false)

// 用 undefined 而不是 null：antd 的 Select 不接受 null 作为 value（清空时回传 undefined）
const query = reactive({
  biz_type: undefined as string | undefined,
  action: undefined as string | undefined,
  keyword: '',
  range: undefined as [string, string] | undefined,
})
const paging = reactive({ page: 1, size: 20, total: 0 })

const columns = [
  { title: '时间', key: 'created_at', width: 150 },
  { title: '操作人', key: 'actor', width: 130 },
  { title: '对象类型', key: 'biz_type', width: 110 },
  { title: '对象 ID', dataIndex: 'biz_id', key: 'biz_id', width: 90 },
  { title: '动作', key: 'action', width: 110 },
  { title: '摘要', dataIndex: 'summary', key: 'summary' },
  { title: 'IP', dataIndex: 'ip', key: 'ip', width: 130 },
]

const bizOptions = Object.entries(AUDIT_BIZ_LABELS).map(([value, label]) => ({ value, label }))
const actionOptions = Object.entries(AUDIT_ACTION_LABELS).map(([value, label]) => ({
  value,
  label,
}))

function params(): AuditQuery {
  return {
    biz_type: query.biz_type,
    action: query.action,
    keyword: query.keyword || undefined,
    created_from: query.range?.[0] || undefined,
    created_to: query.range?.[1] || undefined,
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await auditApi.list({ ...params(), page: paging.page, size: paging.size })
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

function reset(): void {
  query.biz_type = undefined
  query.action = undefined
  query.keyword = ''
  query.range = undefined
  search()
}

function onTableChange(pagination: { current?: number; pageSize?: number }): void {
  paging.page = pagination.current ?? 1
  paging.size = pagination.pageSize ?? 20
  void load()
}

async function exportCsv(): Promise<void> {
  exporting.value = true
  try {
    await downloadFile(auditApi.exportUrl(params()), 'audit.csv')
    feedback.success('已开始下载')
  } catch {
    // 拦截器已提示
  } finally {
    exporting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <div class="page-toolbar">
        <Space wrap>
          <Input
            v-model:value="query.keyword"
            placeholder="摘要 / 操作人"
            allow-clear
            style="width: 190px"
            @press-enter="search"
          />
          <Select
            v-model:value="query.biz_type"
            :options="bizOptions"
            placeholder="对象类型"
            style="width: 150px"
            allow-clear
            @change="search"
          />
          <Select
            v-model:value="query.action"
            :options="actionOptions"
            placeholder="动作"
            style="width: 140px"
            allow-clear
            @change="search"
          />
          <DatePicker.RangePicker
            v-model:value="query.range"
            value-format="YYYY-MM-DD"
            @change="search"
          />
          <Button type="primary" @click="search">查询</Button>
          <Button @click="reset">
            <template #icon><ReloadOutlined /></template>
            重置
          </Button>
        </Space>
        <Space>
          <Button :loading="exporting" @click="exportCsv">
            <template #icon><DownloadOutlined /></template>
            导出 CSV
          </Button>
          <span class="text-muted">共 {{ paging.total }} 条（只增不改）</span>
        </Space>
      </div>

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        row-key="id"
        size="middle"
        :scroll="{ x: 1100 }"
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
          <template v-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>

          <template v-else-if="column.key === 'actor'">
            <span v-if="record.actor_name">{{ record.actor_name }}</span>
            <span v-else class="text-muted">系统</span>
          </template>

          <template v-else-if="column.key === 'biz_type'">
            <Tag>{{ AUDIT_BIZ_LABELS[record.biz_type] ?? record.biz_type }}</Tag>
          </template>

          <template v-else-if="column.key === 'action'">
            <Tag :color="record.action === 'DELETE' ? 'red' : 'blue'">
              {{ AUDIT_ACTION_LABELS[record.action] ?? record.action }}
            </Tag>
          </template>

          <template v-else-if="column.key === 'summary'">
            {{ record.summary || '—' }}
            <a-popover v-if="record.detail" title="详情">
              <template #content>
                <pre class="detail">{{ JSON.stringify(record.detail, null, 2) }}</pre>
              </template>
              <a class="detail-link">详情</a>
            </a-popover>
          </template>

          <template v-else-if="column.key === 'ip'">
            <span class="text-mono">{{ record.ip || '—' }}</span>
          </template>
        </template>
      </Table>
    </Card>
  </div>
</template>

<style scoped lang="scss">
.detail-link {
  margin-left: 6px;
  font-size: 12px;
}

.detail {
  max-width: 420px;
  max-height: 300px;
  margin: 0;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

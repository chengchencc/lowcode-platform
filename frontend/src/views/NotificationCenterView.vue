<script setup lang="ts">
/**
 * 消息中心（F7.1）。
 *
 * 列表与角标轮询共用 `notificationApi`；轮询本身在 DefaultLayout 里做，
 * 这样在任意页面都能看到新待办（F7.2「≤10s 感知」）。
 */
import { CheckOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { Button, Card, Select, Space, Table, Tag } from 'ant-design-vue'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { notificationApi } from '@/api/modules/instance'
import type { NotificationItem } from '@/types/instance'
import { NOTIF_TYPE_LABELS, notifColor } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const router = useRouter()

const rows = ref<NotificationItem[]>([])
const loading = ref(false)
const query = reactive({ unread_only: false, type: undefined as string | undefined })
const paging = reactive({ page: 1, size: 20, total: 0 })

const columns = [
  { title: '类型', key: 'type', width: 110 },
  { title: '标题', key: 'title' },
  { title: '内容', key: 'content', width: 280 },
  { title: '时间', key: 'created_at', width: 150 },
  { title: '操作', key: 'action', width: 110, fixed: 'right' as const },
]

const typeOptions = Object.entries(NOTIF_TYPE_LABELS).map(([value, label]) => ({ value, label }))

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await notificationApi.list({
      page: paging.page,
      size: paging.size,
      unread_only: query.unread_only,
      type: query.type,
    })
    rows.value = data.items
    paging.total = data.total
  } finally {
    loading.value = false
  }
}

onMounted(load)

function search(): void {
  paging.page = 1
  void load()
}

function onTableChange(pagination: { current?: number; pageSize?: number }): void {
  paging.page = pagination.current ?? 1
  paging.size = pagination.pageSize ?? 20
  void load()
}

async function markRead(row: NotificationItem): Promise<void> {
  await notificationApi.markRead(row.id)
  await load()
}

/** 勾选只能勾未读的（已读的没有「再读一次」这回事），所以直接按 id 批量提交 */
const selectedKeys = ref<number[]>([])

function onSelectChange(keys: (number | string)[]): void {
  selectedKeys.value = keys.map(Number)
}

async function markSelectedRead(): Promise<void> {
  if (!selectedKeys.value.length) return
  await notificationApi.markManyRead(selectedKeys.value)
  feedback.success(`已标记 ${selectedKeys.value.length} 条为已读`)
  selectedKeys.value = []
  await load()
}

/** 未读行整行淡色底 —— 一屏几十条时比看小红点快得多 */
function rowClassName(row: NotificationItem): string {
  return row.is_read ? '' : 'row-unread'
}

async function markAllRead(): Promise<void> {
  const result = await notificationApi.markAllRead()
  feedback.success(result.message ?? '已全部标记为已读')
  selectedKeys.value = []
  await load()
}

/** 跳到消息关联的页面（待办直达实例详情） */
function open(row: NotificationItem): void {
  const link = row.link
  if (!link) return
  if (!row.is_read) void notificationApi.markRead(row.id)
  void router.push(link)
}
</script>

<template>
  <div class="page-container">
    <Card :bordered="false">
      <div class="page-toolbar">
        <Space>
          <Select
            v-model:value="query.type"
            :options="typeOptions"
            placeholder="消息类型"
            style="width: 140px"
            allow-clear
            @change="search"
          />
          <a-checkbox v-model:checked="query.unread_only" @change="search">只看未读</a-checkbox>
          <Button @click="load">
            <template #icon><ReloadOutlined /></template>
            刷新
          </Button>
        </Space>
        <Space>
          <Button v-if="selectedKeys.length" @click="markSelectedRead">
            <template #icon><CheckOutlined /></template>
            已读所选（{{ selectedKeys.length }}）
          </Button>
          <Button @click="markAllRead">
            <template #icon><CheckOutlined /></template>
            全部已读
          </Button>
        </Space>
      </div>

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        row-key="id"
        size="middle"
        :row-class-name="rowClassName"
        :row-selection="{
          selectedRowKeys: selectedKeys,
          onChange: onSelectChange,
          getCheckboxProps: (row: NotificationItem) => ({ disabled: row.is_read }),
        }"
        :scroll="{ x: 900 }"
        :pagination="{
          current: paging.page, pageSize: paging.size, total: paging.total,
          showTotal: (t: number) => `共 ${t} 条`,
        }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'type'">
            <Tag :color="notifColor(record.type)">
              {{ NOTIF_TYPE_LABELS[record.type] ?? record.type }}
            </Tag>
          </template>

          <template v-else-if="column.key === 'title'">
            <a @click="open(record as NotificationItem)">{{ record.title }}</a>
            <Tag v-if="!record.is_read" color="red" class="unread">未读</Tag>
          </template>

          <template v-else-if="column.key === 'content'">
            <span :class="{ 'text-muted': true }">{{ record.content || '—' }}</span>
          </template>

          <template v-else-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>

          <template v-else-if="column.key === 'action'">
            <Space :size="2">
              <Button type="link" size="small" @click="open(record as NotificationItem)">
                查看
              </Button>
              <Button
                v-if="!record.is_read"
                type="link"
                size="small"
                @click="markRead(record as NotificationItem)"
              >
                已读
              </Button>
            </Space>
          </template>
        </template>
      </Table>
    </Card>
  </div>
</template>

<style scoped>
.unread {
  margin-left: 6px;
  font-size: 10px;
}

.row-unread :deep(td) {
  background: #fffbe6;
}
</style>

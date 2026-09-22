<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import { onMounted, reactive, ref } from 'vue'

import { auditApi, type AuditLogItem } from '@/api/modules/role'
import { AUDIT_ACTION_LABELS, AUDIT_BIZ_LABELS } from '@/stores/app'
import { formatDateTime } from '@/utils/datetime'


const rows = ref<AuditLogItem[]>([])
const loading = ref(false)
// 用 undefined 而不是 null：antd 的 Select 不接受 null 作为 value（清空时回传 undefined）
const query = reactive({ biz_type: undefined as string | undefined })
const paging = reactive({ page: 1, size: 20, total: 0 })

const columns = [
  { title: '时间', key: 'created_at', width: 150 },
  { title: '操作人', key: 'actor', width: 130 },
  { title: '对象类型', key: 'biz_type', width: 110 },
  { title: '对象 ID', dataIndex: 'biz_id', key: 'biz_id', width: 90 },
  { title: '动作', key: 'action', width: 100 },
  { title: '摘要', dataIndex: 'summary', key: 'summary' },
  { title: 'IP', dataIndex: 'ip', key: 'ip', width: 130 },
]

const bizOptions = Object.entries(AUDIT_BIZ_LABELS).map(([value, label]) => ({ value, label }))

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await auditApi.list({
      page: paging.page,
      size: paging.size,
      biz_type: query.biz_type,
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

function onTableChange(pagination: { current?: number; pageSize?: number }): void {
  paging.page = pagination.current ?? 1
  paging.size = pagination.pageSize ?? 20
  void load()
}

onMounted(load)
</script>

<template>
  <div class="page-container">
    <a-card :bordered="false">
      <div class="page-toolbar">
        <a-space>
          <a-select             v-model:value="query.biz_type"
            :options="bizOptions"
            placeholder="对象类型"
            style="width: 150px"
            allow-clear
          />
          <a-button type="primary" @click="search">查询</a-button>
          <a-button             @click="
              () => {
                query.biz_type = undefined
                search()
              }
            "
          >
            <template #icon><ReloadOutlined /></template>
            重置
          </a-button>
        </a-space>
        <span class="text-muted">共 {{ paging.total }} 条记录（只增不改）</span>
      </div>

      <a-table         :columns="columns"
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
            <a-tag>{{ AUDIT_BIZ_LABELS[record.biz_type] ?? record.biz_type }}</a-tag>
          </template>

          <template v-else-if="column.key === 'action'">
            <a-tag :color="record.action === 'DELETE' ? 'red' : 'blue'">
              {{ AUDIT_ACTION_LABELS[record.action] ?? record.action }}
            </a-tag>
          </template>

          <template v-else-if="column.key === 'summary'">
            {{ record.summary || '—' }}
          </template>

          <template v-else-if="column.key === 'ip'">
            <span class="text-mono">{{ record.ip || '—' }}</span>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

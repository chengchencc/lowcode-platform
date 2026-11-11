<script setup lang="ts">
import { Card } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import type { DashboardWorkStatItem } from '@/types/dashboard'
import { formatDateTime } from '@/utils/datetime'

defineProps<{ sheets: DashboardWorkStatItem[] }>()

const router = useRouter()

function open(item: DashboardWorkStatItem): void {
  void router.push({ name: 'work-stat-sheet', params: { id: item.sheet_id } })
}
</script>

<template>
  <Card title="工作量统计" :bordered="false" class="block work-stats-card">
    <template #extra>
      <a @click="router.push({ name: 'work-stats' })">全部</a>
    </template>

    <div
      v-for="item in sheets"
      :key="item.sheet_id"
      class="sheet-row"
      @click="open(item)"
    >
      <span class="sheet-name">{{ item.name }}</span>
      <span class="text-muted sheet-time">{{ formatDateTime(item.updated_at) }}</span>
    </div>
  </Card>
</template>

<style scoped lang="scss">
.work-stats-card {
  height: auto;
}

.sheet-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;

  &:last-child {
    border-bottom: none;
  }

  &:hover .sheet-name {
    color: #1677ff;
  }
}

.sheet-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.sheet-time {
  flex: 0 0 auto;
  font-size: 12px;
}
</style>

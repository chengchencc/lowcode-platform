<script setup lang="ts">
import { Card, Empty, Tag } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import type { DashboardInstanceItem } from '@/types/dashboard'
import { INSTANCE_STATUS_META } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'

defineProps<{ title: string; instances: DashboardInstanceItem[] }>()

const router = useRouter()

function open(item: DashboardInstanceItem): void {
  void router.push({ name: 'instance-detail', params: { id: item.instance_id } })
}
</script>

<template>
  <Card :title="title" :bordered="false" class="block">
    <template #extra>
      <a @click="router.push({ name: 'workbench', params: { type: 'mine' } })">全部</a>
    </template>

    <template v-if="instances.length">
      <div
        v-for="item in instances"
        :key="item.instance_id"
        class="instance-item"
        @click="open(item)"
      >
        <div class="instance-title">
          <span class="instance-name">{{ item.title }}</span>
          <Tag :color="INSTANCE_STATUS_META[item.status]?.color">
            {{ INSTANCE_STATUS_META[item.status]?.text ?? item.status }}
          </Tag>
        </div>
        <div class="instance-meta text-muted">
          <span v-if="item.current_node_names.length">
            当前：{{ item.current_node_names.join('、') }}
          </span>
          <span>{{ formatDateTime(item.updated_at) }}</span>
        </div>
      </div>
    </template>
    <Empty v-else description="还没有发起过单据" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
  </Card>
</template>

<style scoped lang="scss">
.instance-item {
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;

  &:last-child {
    border-bottom: none;
  }

  &:hover .instance-name {
    color: #1677ff;
  }
}

.instance-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
}

.instance-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.instance-meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
}
</style>

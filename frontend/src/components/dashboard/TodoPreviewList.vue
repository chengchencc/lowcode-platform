<script setup lang="ts">
import { Card, Empty, Tag } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import type { DashboardTodoItem } from '@/types/dashboard'
import { formatDateTime } from '@/utils/datetime'

defineProps<{ todos: DashboardTodoItem[] }>()

const router = useRouter()

function open(item: DashboardTodoItem): void {
  void router.push({
    name: 'instance-detail',
    params: { id: item.instance_id },
    query: { assignment: item.assignment_id },
  })
}
</script>

<template>
  <Card title="我的待办" :bordered="false" class="block">
    <template #extra>
      <a @click="router.push({ name: 'workbench', params: { type: 'todo' } })">全部待办</a>
    </template>

    <template v-if="todos.length">
      <div
        v-for="item in todos"
        :key="item.assignment_id"
        class="todo-item"
        @click="open(item)"
      >
        <div class="todo-title">{{ item.title }}</div>
        <div class="todo-meta text-muted">
          <span class="text-mono">{{ item.code }}</span>
          <Tag v-if="item.node_name" class="todo-node">{{ item.node_name }}</Tag>
          <span>{{ formatDateTime(item.arrived_at) }}</span>
        </div>
      </div>
    </template>
    <Empty v-else description="暂无待办" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
  </Card>
</template>

<style scoped lang="scss">
.todo-item {
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;

  &:last-child {
    border-bottom: none;
  }

  &:hover .todo-title {
    color: #1677ff;
  }
}

.todo-title {
  font-size: 13px;
  font-weight: 500;
}

.todo-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
}

.todo-node {
  margin: 0;
  font-size: 11px;
}
</style>

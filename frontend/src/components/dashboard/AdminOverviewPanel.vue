<script setup lang="ts">
import { Card, Col, Empty, Row, Statistic } from 'ant-design-vue'

import type { DashboardAdmin } from '@/types/dashboard'

defineProps<{ admin: DashboardAdmin }>()
</script>

<template>
  <Card title="全局概览" :bordered="false" class="block">
    <Row :gutter="[8, 8]">
      <Col :xs="12" :sm="6">
        <Statistic title="运行中" :value="admin.running" />
      </Col>
      <Col :xs="12" :sm="6">
        <Statistic title="今日提交" :value="admin.submitted_today" />
      </Col>
      <Col :xs="12" :sm="6">
        <Statistic title="本周完成" :value="admin.finished_this_week" />
      </Col>
      <Col :xs="12" :sm="6">
        <Statistic title="待办积压" :value="admin.pending_backlog" />
      </Col>
    </Row>

    <div class="by-flow">
      <div class="text-muted by-flow-title">运行中流程 Top 5</div>
      <template v-if="admin.by_flow.length">
        <div v-for="item in admin.by_flow" :key="item.flow_template_id" class="by-flow-row">
          <span class="by-flow-name">{{ item.name }}</span>
          <strong>{{ item.count }}</strong>
        </div>
      </template>
      <Empty v-else description="暂无运行中流程" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
    </div>
  </Card>
</template>

<style scoped lang="scss">
.by-flow {
  margin-top: 16px;
}

.by-flow-title {
  margin-bottom: 4px;
  font-size: 12px;
}

.by-flow-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f5f5f5;
  font-size: 13px;

  &:last-child {
    border-bottom: none;
  }
}

.by-flow-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

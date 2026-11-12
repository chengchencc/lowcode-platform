<script setup lang="ts">
import { Card, Col, Row, Statistic } from 'ant-design-vue'

import type { DashboardStats } from '@/types/dashboard'

defineProps<{ stats: DashboardStats }>()
</script>

<template>
  <Row :gutter="[12, 12]">
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="待办" :value="stats.todo" />
      </Card>
    </Col>
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="抄送未读" :value="stats.cc_unread" />
      </Card>
    </Col>
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="我发起的进行中" :value="stats.mine_running" />
      </Card>
    </Col>
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="本月已完成" :value="stats.mine_finished_this_month" />
      </Card>
    </Col>
  </Row>
</template>

<style scoped lang="scss">
.stat-card {
  height: 100%;
  border-radius: 8px;

  :deep(.ant-statistic-title) {
    font-size: 12px;
  }

  :deep(.ant-statistic-content) {
    font-size: 24px;
  }
}
</style>

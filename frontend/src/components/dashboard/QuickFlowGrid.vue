<script setup lang="ts">
import { RocketOutlined } from '@ant-design/icons-vue'
import { Card, Col, Empty, Row } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import type { DashboardFlowItem } from '@/types/dashboard'

defineProps<{ flows: DashboardFlowItem[] }>()

const router = useRouter()

function start(flow: DashboardFlowItem): void {
  void router.push({
    name: 'start-form',
    params: { flowTemplateId: flow.flow_template_id },
  })
}
</script>

<template>
  <Card title="常用流程" :bordered="false" class="block">
    <template #extra>
      <a @click="router.push({ name: 'start-center' })">发起中心</a>
    </template>

    <Row v-if="flows.length" :gutter="[8, 8]">
      <Col v-for="flow in flows" :key="flow.flow_template_id" :xs="12" :sm="8">
        <button type="button" class="flow-card" @click="start(flow)">
          <RocketOutlined />
          <span class="flow-name">{{ flow.name }}</span>
        </button>
      </Col>
    </Row>
    <Empty v-else description="暂无可发起的流程" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
  </Card>
</template>

<style scoped lang="scss">
.flow-card {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fff;
  color: rgba(0, 0, 0, 0.75);
  cursor: pointer;
  text-align: left;

  &:hover {
    border-color: #91caff;
    color: #1677ff;
  }
}

.flow-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

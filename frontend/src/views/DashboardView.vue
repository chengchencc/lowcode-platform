<script setup lang="ts">
import { Col, Empty, Row, Spin } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { dashboardApi } from '@/api/modules/dashboard'
import AdminOverviewPanel from '@/components/dashboard/AdminOverviewPanel.vue'
import InstancePreviewList from '@/components/dashboard/InstancePreviewList.vue'
import QuickFlowGrid from '@/components/dashboard/QuickFlowGrid.vue'
import StatTiles from '@/components/dashboard/StatTiles.vue'
import TodoPreviewList from '@/components/dashboard/TodoPreviewList.vue'
import { useAuthStore } from '@/stores/auth'
import type { DashboardOverview } from '@/types/dashboard'

/** 首页轮询：待办角标与预览保持 ≤10s 感知（与 DefaultLayout 的角标轮询一致） */
const POLL_INTERVAL_MS = 10_000

const auth = useAuthStore()
const data = ref<DashboardOverview | null>(null)
const loading = ref(false)
const showAdmin = computed(() => auth.isAdmin || auth.isDesigner)

let pollTimer: ReturnType<typeof setInterval> | null = null

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    data.value = await dashboardApi.overview()
  } catch {
    // 首页失败不打断其他页面；静默保留上一次数据，轮询会自动重试
  } finally {
    if (!silent) loading.value = false
  }
}

onMounted(() => {
  void load()
  pollTimer = setInterval(() => void load(true), POLL_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="page-container dashboard">
    <div class="welcome">
      <h2 class="welcome-title">你好，{{ auth.displayName }}</h2>
      <div class="text-muted welcome-meta">
        <span v-if="auth.user?.dept_name">{{ auth.user.dept_name }}</span>
        <span v-if="auth.user?.roles.length">
          {{ auth.user.roles.map((role) => role.name).join(' / ') }}
        </span>
      </div>
    </div>

    <Spin :spinning="loading">
      <template v-if="data">
        <StatTiles :stats="data.personal" />

        <Row :gutter="[12, 12]" class="dashboard-row">
          <Col :xs="24" :lg="14">
            <TodoPreviewList :todos="data.todos" />
          </Col>
          <Col :xs="24" :lg="10">
            <QuickFlowGrid :flows="data.quick_flows" />
          </Col>
        </Row>

        <Row :gutter="[12, 12]" class="dashboard-row">
          <Col :xs="24" :lg="showAdmin && data.admin ? 14 : 24">
            <InstancePreviewList title="我发起的" :instances="data.my_instances" />
          </Col>
          <Col v-if="showAdmin && data.admin" :xs="24" :lg="10">
            <AdminOverviewPanel :admin="data.admin" />
          </Col>
        </Row>
      </template>
      <Empty v-else-if="!loading" description="暂无数据" />
    </Spin>
  </div>
</template>

<style scoped lang="scss">
.dashboard {
  max-width: 1440px;
  margin: 0 auto;
}

.welcome {
  padding: 4px 0 16px;
}

.welcome-title {
  margin: 0;
  font-size: 20px;
}

.welcome-meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
}

.dashboard-row {
  margin-top: 12px;
}

.block {
  height: 100%;
  border-radius: 8px;
}
</style>

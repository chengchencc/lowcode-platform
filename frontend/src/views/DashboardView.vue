<script setup lang="ts">

import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/datetime'


const auth = useAuthStore()

/** M1 已交付的能力；后续里程碑完成后逐条替换为真实入口。 */
const milestones = [
  { key: 'M1', title: '骨架与组织', desc: '登录鉴权、用户 / 部门 / 角色、操作审计', done: true },
  { key: 'M2', title: '表单', desc: '表单模板配置器、通用表单渲染器', done: true },
  { key: 'M3', title: '流程定义 + 引擎', desc: '流程配置器、审批引擎（顺序/会签/或签/条件）', done: true },
  { key: 'M4', title: '发起与工作台', desc: '发起中心、待办工作台、实例详情页', done: true },
  { key: 'M5', title: '字段累积增强', desc: '驳回重提、运行中追加字段、公式字段', done: true },
  { key: 'M6', title: '打磨与上线', desc: '示例流程、归档导出、Docker 部署', done: false },
]
</script>

<template>
  <div class="page-container">
    <a-card class="welcome-card" :bordered="false">
      <h2>你好，{{ auth.displayName }}</h2>
      <p class="text-muted">
        欢迎使用 FlowForm。当前处于 <strong>M1（骨架与组织）</strong> 阶段，
        登录与组织管理已经可用；表单配置与审批流将在后续里程碑开放。
      </p>
      <a-descriptions :column="{ xs: 1, sm: 2 }" size="small" bordered style="margin-top: 16px">
        <a-descriptions-item label="账号">{{ auth.user?.username }}</a-descriptions-item>
        <a-descriptions-item label="所属部门">
          {{ auth.user?.dept_name ?? '未分配' }}
        </a-descriptions-item>
        <a-descriptions-item label="角色">
          <template v-if="auth.user?.roles.length">
            <a-tag v-for="role in auth.user.roles" :key="role.code" color="blue">
              {{ role.name }}
            </a-tag>
          </template>
          <span v-else class="text-muted">无</span>
        </a-descriptions-item>
        <a-descriptions-item label="上次登录">
          {{ formatDateTime(auth.user?.last_login_at) }}
        </a-descriptions-item>
      </a-descriptions>
    </a-card>

    <a-card title="里程碑进度" :bordered="false" style="margin-top: 16px">
      <ul class="milestones">
        <li v-for="item in milestones" :key="item.key" :class="{ done: item.done }">
          <a-tag :color="item.done ? 'green' : 'default'">{{ item.key }}</a-tag>
          <div class="milestone-body">
            <strong>{{ item.title }}</strong>
            <span class="text-muted">{{ item.desc }}</span>
          </div>
          <span class="milestone-state">{{ item.done ? '已完成' : '待开发' }}</span>
        </li>
      </ul>
    </a-card>
  </div>
</template>

<style scoped lang="scss">
.welcome-card h2 {
  margin: 0 0 8px;
  font-size: 20px;
}

.milestones {
  list-style: none;
  margin: 0;
  padding: 0;

  li {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid #f0f0f0;

    &:last-child {
      border-bottom: none;
    }
  }
}

.milestone-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  font-size: 13px;
}

.milestone-state {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

li.done .milestone-state {
  color: #52c41a;
}
</style>

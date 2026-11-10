<script setup lang="ts">
/**
 * 打印文档（M10）。
 *
 * 屏幕上隐藏，`window.print()` 时由全局打印样式显示。用只读 FormRenderer
 * 复用同一套表单渲染逻辑，避免打印版与页面版两套字段结构。
 */
import { computed } from 'vue'

import { FormRenderer } from '@/components/form-renderer'
import type { FieldState, FormRule } from '@/types/form'
import type { InstanceRender } from '@/types/instance'
import { INSTANCE_STATUS_META } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'

const props = defineProps<{
  data: InstanceRender
  values: Record<string, unknown>
  permissions: Record<string, FieldState>
  rules: FormRule[]
}>()

const statusLabel = computed(
  () => INSTANCE_STATUS_META[props.data.instance.status]?.text ?? props.data.instance.status,
)

const actions = computed(() => props.data.actions)
</script>

<template>
  <div class="print-document">
    <header class="print-header">
      <h1>{{ data.instance.title }}</h1>
      <div class="print-meta">
        <span>单号：{{ data.instance.code }}</span>
        <span>状态：{{ statusLabel }}</span>
        <span>流程：{{ data.instance.flow_template_name }}</span>
      </div>
      <div class="print-meta">
        <span>发起人：{{ data.instance.initiator_name }}</span>
        <span>发起部门：{{ data.instance.initiator_dept_name || '—' }}</span>
        <span>提交时间：{{ formatDateTime(data.instance.started_at) || '—' }}</span>
        <span>完成时间：{{ formatDateTime(data.instance.finished_at) || '—' }}</span>
      </div>
    </header>

    <FormRenderer
      :schema="data.schema_data"
      :model-value="values"
      :permissions="permissions"
      :rules="rules"
      mode="readonly"
    />

    <section class="print-history">
      <h2>处理历史</h2>
      <table v-if="actions.length">
        <thead>
          <tr>
            <th>时间</th>
            <th>操作</th>
            <th>节点</th>
            <th>处理人</th>
            <th>意见</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="action in actions" :key="action.action_id">
            <td>{{ formatDateTime(action.created_at) }}</td>
            <td>{{ action.action_label }}</td>
            <td>{{ action.node_name || '—' }}</td>
            <td>{{ action.actor_name }}</td>
            <td>{{ action.opinion || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted">暂无处理记录</p>
    </section>
  </div>
</template>

<style scoped lang="scss">
.print-document {
  color: #000;
  background: #fff;
  font-size: 12px;
}

.print-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #000;
}

.print-header h1 {
  margin: 0 0 10px;
  font-size: 22px;
  text-align: center;
}

.print-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  margin-top: 4px;
  color: rgba(0, 0, 0, 0.75);
}

.print-history {
  margin-top: 18px;
  break-inside: avoid;
}

.print-history h2 {
  margin: 0 0 8px;
  font-size: 15px;
}

.print-history table {
  width: 100%;
  border-collapse: collapse;
}

.print-history th,
.print-history td {
  padding: 4px 6px;
  border: 1px solid #999;
  text-align: left;
  vertical-align: top;
}

.print-history th {
  background: #f0f0f0;
  font-weight: 600;
}
</style>

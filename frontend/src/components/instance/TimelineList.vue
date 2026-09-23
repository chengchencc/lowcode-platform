<script setup lang="ts">
/**
 * 处理历史时间线（F4.6）。
 *
 * 每条动作展开后可看：审批意见、**字段变更对照（旧值→新值）**、附件，
 * 以及「查看当时的快照」入口 —— 争议追溯靠的就是这个。
 */
import { ClockCircleOutlined, HistoryOutlined } from '@ant-design/icons-vue'
import { Tag, Timeline } from 'ant-design-vue'
import { ref } from 'vue'

import type { ActionEntry } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'
import { downloadFile } from '@/utils/download'
import { feedback } from '@/utils/feedback'

defineProps<{
  actions: ActionEntry[]
  /** 已选中的快照 id（用于高亮） */
  activeSnapshotId?: number | null
}>()

const emit = defineEmits<{ 'view-snapshot': [snapshotId: number] }>()

const ATimeline = Timeline
const ATimelineItem = Timeline.Item
const ATag = Tag

async function downloadAttachment(att: { id: number; file_name: string }): Promise<void> {
  try {
    await downloadFile(`/files/${att.id}/download`, att.file_name)
  } catch {
    feedback.error('附件下载失败（可能没有权限）')
  }
}

const expanded = ref<Set<number>>(new Set())

function toggle(actionId: number): void {
  const next = new Set(expanded.value)
  if (next.has(actionId)) next.delete(actionId)
  else next.add(actionId)
  expanded.value = next
}

function isExpanded(actionId: number): boolean {
  return expanded.value.has(actionId)
}

/** 动作 → 时间线节点的颜色 */
function colorOf(action: string): string {
  if (action === 'REJECT') return 'red'
  if (action === 'RETURN') return 'orange'
  if (action === 'AGREE' || action === 'SUBMIT') return 'green'
  if (action === 'TERMINATE') return 'gray'
  return 'blue'
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '（空）'
  if (Array.isArray(value)) {
    if (!value.length) return '（空）'
    // 子表：显示行数；普通数组：拼起来
    if (typeof value[0] === 'object' && value[0] !== null) return `${value.length} 行`
    return value.map((v) => String(v)).join('、')
  }
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function hasDetail(action: ActionEntry): boolean {
  return Boolean(
    action.opinion ||
      action.changed_fields?.length ||
      action.attachments?.length ||
      action.snapshot_id,
  )
}
</script>

<template>
  <div class="timeline-list">
    <ATimeline v-if="actions.length">
      <ATimelineItem v-for="action in actions" :key="action.action_id" :color="colorOf(action.action)">
        <div class="head">
          <span class="actor">{{ action.actor_name }}</span>
          <ATag class="action-tag">{{ action.action_label }}</ATag>
          <span v-if="action.node_name" class="text-muted node">{{ action.node_name }}</span>
          <span v-if="action.round > 1" class="text-muted round">第 {{ action.round }} 轮</span>
          <span class="spacer" />
          <span class="text-muted time">
            <ClockCircleOutlined />
            {{ formatDateTime(action.created_at) }}
          </span>
          <a v-if="hasDetail(action)" class="toggle" @click="toggle(action.action_id)">
            {{ isExpanded(action.action_id) ? '收起' : '详情' }}
          </a>
        </div>

        <div v-if="isExpanded(action.action_id)" class="detail">
          <div v-if="action.opinion" class="opinion">
            <span class="field-label">意见：</span>{{ action.opinion }}
          </div>

          <div v-if="action.changed_fields?.length" class="changes">
            <div class="field-label">字段变更：</div>
            <div v-for="change in action.changed_fields" :key="change.key" class="change-row">
              <span class="change-label">{{ change.label }}</span>
              <span class="old">{{ formatValue(change.old) }}</span>
              <span class="arrow">→</span>
              <span class="new">{{ formatValue(change.new) }}</span>
            </div>
          </div>

          <div v-if="action.attachments?.length" class="attachments">
            <span class="field-label">附件：</span>
            <!-- 不能用 <a href>：下载接口只认 Authorization 头，点链接会 401 -->
            <a
              v-for="att in action.attachments"
              :key="att.id"
              class="attachment"
              @click="downloadAttachment(att)"
            >
              {{ att.file_name }}
            </a>
          </div>

          <div v-if="action.snapshot_id" class="snapshot-link">
            <a
              :class="{ active: activeSnapshotId === action.snapshot_id }"
              @click="emit('view-snapshot', action.snapshot_id as number)"
            >
              <HistoryOutlined />
              查看当时的表单快照（#{{ action.snapshot_seq }}）
            </a>
          </div>
        </div>
      </ATimelineItem>
    </ATimeline>

    <a-empty v-else description="还没有处理记录" />
  </div>
</template>

<style scoped lang="scss">
.timeline-list {
  :deep(.ant-timeline-item) {
    padding-bottom: 16px;
  }
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}

.actor {
  font-weight: 600;
}

.action-tag {
  margin: 0;
}

.node {
  font-size: 12px;
}

.round {
  font-size: 11px;
}

.spacer {
  flex: 1;
}

.time {
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.toggle {
  font-size: 12px;
}

.detail {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  background: #fafafa;
  font-size: 12px;
}

.field-label {
  color: rgba(0, 0, 0, 0.45);
}

.opinion {
  margin-bottom: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

.changes {
  margin-bottom: 8px;
}

.change-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
}

.change-label {
  flex: 0 0 auto;
  min-width: 90px;
  color: rgba(0, 0, 0, 0.65);
}

.old {
  color: rgba(0, 0, 0, 0.45);
  text-decoration: line-through;
}

.arrow {
  color: rgba(0, 0, 0, 0.35);
}

.new {
  color: #1677ff;
  font-weight: 500;
}

.attachments {
  margin-bottom: 8px;
}

.attachment {
  margin-right: 10px;
}

.snapshot-link a {
  display: inline-flex;
  align-items: center;
  gap: 4px;

  &.active {
    font-weight: 600;
  }
}
</style>

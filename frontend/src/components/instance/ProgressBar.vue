<script setup lang="ts">
/**
 * 流程进度条（PRD F4.2）。
 *
 * 三种结构各有展示方式：
 * - **顺序节点**：横向排列，当前节点高亮
 * - **并行组**：组内成员**并列**（不是串联），否则会误导成「一个一个来」
 * - **条件分支**：只亮实际走的那条，其余灰显 —— 「为什么没走另一边」一眼可见
 *
 * 纵向排布而不是横条：分支与并行嵌套后横向空间不够，
 * 硬塞进去会让节点名被截断。
 */
import { computed } from 'vue'

import type { ProgressNode } from '@/types/instance'
import { NODE_STATUS_META } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'

const props = defineProps<{
  nodes: ProgressNode[]
  /** 当前查看的节点（会签组内并列时高亮） */
  activeNodeId?: string | null
}>()

function statusOf(node: ProgressNode): string {
  return node.status ?? 'PENDING'
}

function metaOf(node: ProgressNode) {
  return NODE_STATUS_META[statusOf(node)] ?? NODE_STATUS_META.PENDING
}

function isActive(node: ProgressNode): boolean {
  return props.activeNodeId === node.node_id || statusOf(node) === 'ACTIVE'
}

/** 该节点上已处理的处理人（同意/驳回/退回），用于在进度条上直接显示结果 */
function decidedAssignees(node: ProgressNode) {
  return (node.assignees ?? []).filter((a) => a.status === 'DONE')
}

function pendingAssignees(node: ProgressNode) {
  return (node.assignees ?? []).filter((a) => a.status === 'PENDING' || a.status === 'WAITING')
}

const CONDITION_TAKEN_HINT = '（本次走这条）'
const CONDITION_SKIPPED_HINT = '（未走）'

const hasAnyNode = computed(() => props.nodes.length > 0)
</script>

<template>
  <div class="progress-bar">
    <template v-if="hasAnyNode">
      <div
        v-for="(node, index) in nodes"
        :key="node.node_id"
        class="step"
        :class="{ active: isActive(node) }"
      >
        <div class="marker">
          <span class="dot" :class="`dot-${statusOf(node).toLowerCase()}`" />
          <span v-if="index < nodes.length - 1" class="line" />
        </div>

        <div class="body">
          <!-- ---------------- 条件分支 ---------------- -->
          <template v-if="node.type === 'condition'">
            <div class="node-title">{{ node.name }}</div>
            <div class="branches">
              <div
                v-for="branch in node.branches ?? []"
                :key="branch.branch_id"
                class="branch"
                :class="{ taken: branch.taken, skipped: !branch.taken }"
              >
                <div class="branch-head">
                  <span class="branch-name">{{ branch.name }}</span>
                  <span class="branch-hint">
                    {{ branch.taken ? CONDITION_TAKEN_HINT : CONDITION_SKIPPED_HINT }}
                  </span>
                </div>
                <div v-if="branch.nodes.length" class="branch-nodes">
                  <div
                    v-for="child in branch.nodes"
                    :key="child.node_id"
                    class="sub-node"
                    :class="{ active: isActive(child) }"
                  >
                    <span class="dot small" :class="`dot-${statusOf(child).toLowerCase()}`" />
                    <span class="sub-name">{{ child.name }}</span>
                    <span class="sub-status">{{ metaOf(child).text }}</span>
                  </div>
                </div>
                <div v-else class="branch-empty">（无节点，直接汇合）</div>
              </div>
            </div>
          </template>

          <!-- ---------------- 并行组 ---------------- -->
          <template v-else-if="node.type === 'parallel'">
            <div class="node-title">
              {{ node.name }}
              <a-tag :color="node.mode === 'any' ? 'orange' : 'blue'" class="mode-tag">
                {{ node.mode === 'any' ? '或签' : '会签' }}
              </a-tag>
              <a-tag :color="metaOf(node).color">{{ metaOf(node).text }}</a-tag>
            </div>
            <!-- 组内成员**并列**展示 -->
            <div class="members">
              <div
                v-for="member in node.members ?? []"
                :key="member.node_id"
                class="member"
                :class="{ active: isActive(member) }"
              >
                <div class="member-head">
                  <span class="dot small" :class="`dot-${statusOf(member).toLowerCase()}`" />
                  <span class="member-name">{{ member.name }}</span>
                  <span class="sub-status">{{ metaOf(member).text }}</span>
                </div>
                <div v-if="member.assignees?.length" class="assignees">
                  <span
                    v-for="a in member.assignees"
                    :key="a.assignment_id"
                    class="assignee"
                    :class="a.status.toLowerCase()"
                  >
                    {{ a.user_name }}
                    <em v-if="a.result === 'AGREE'">✓</em>
                    <em v-else-if="a.result === 'REJECT'">✕</em>
                    <em v-else-if="a.result === 'RETURN'">↩</em>
                  </span>
                </div>
              </div>
            </div>
          </template>

          <!-- ---------------- 普通节点 ---------------- -->
          <template v-else>
            <div class="node-title">
              <span class="name">{{ node.name }}</span>
              <a-tag v-if="node.type !== 'start'" class="type-tag">{{ node.type_label }}</a-tag>
              <a-tag :color="metaOf(node).color">{{ metaOf(node).text }}</a-tag>
              <a-tag v-if="node.activation_seq && node.activation_seq > 1" color="purple" class="type-tag">
                第 {{ node.activation_seq }} 次
              </a-tag>
            </div>

            <div v-if="pendingAssignees(node).length" class="assignees">
              <span class="text-muted label">待办：</span>
              <span v-for="a in pendingAssignees(node)" :key="a.assignment_id" class="assignee pending">
                {{ a.user_name }}
              </span>
            </div>

            <div v-if="decidedAssignees(node).length" class="assignees">
              <span class="text-muted label">已处理：</span>
              <span
                v-for="a in decidedAssignees(node)"
                :key="a.assignment_id"
                class="assignee"
                :class="a.result ? a.result.toLowerCase() : ''"
              >
                {{ a.user_name }}
                <em v-if="a.result === 'AGREE'">✓</em>
                <em v-else-if="a.result === 'REJECT'">✕</em>
                <em v-else-if="a.result === 'RETURN'">↩</em>
                <em v-else-if="a.result === 'READ'">已读</em>
              </span>
            </div>

            <div v-if="node.completed_at" class="text-muted time">
              {{ formatDateTime(node.completed_at) }}
            </div>
          </template>
        </div>
      </div>
    </template>

    <a-empty v-else description="没有流程节点" />
  </div>
</template>

<style scoped lang="scss">
.progress-bar {
  padding: 4px 0;
}

.step {
  display: flex;
  gap: 10px;
}

.marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 0 0 16px;
  padding-top: 4px;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #d9d9d9;
  flex: 0 0 auto;

  &.small {
    width: 8px;
    height: 8px;
  }

  &.dot-completed {
    background: #52c41a;
  }
  &.dot-active {
    background: #1677ff;
    box-shadow: 0 0 0 4px rgb(22 119 255 / 15%);
  }
  &.dot-cancelled {
    background: #ff7875;
  }
  &.dot-pending {
    background: #d9d9d9;
  }
}

.line {
  flex: 1;
  width: 2px;
  min-height: 18px;
  margin: 2px 0;
  background: #f0f0f0;
}

.body {
  flex: 1;
  padding-bottom: 16px;
  min-width: 0;
}

.node-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 14px;
  font-weight: 500;

  .name {
    font-weight: 600;
  }
}

.step.active .node-title .name {
  color: #1677ff;
}

.type-tag,
.mode-tag {
  font-size: 11px;
  margin: 0;
}

.assignees {
  margin-top: 4px;
  font-size: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;

  .label {
    font-size: 11px;
  }
}

.assignee {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  border-radius: 10px;
  background: #f5f5f5;
  color: rgba(0, 0, 0, 0.65);

  &.pending {
    background: #e6f4ff;
    color: #1677ff;
  }
  &.agree {
    background: #f6ffed;
    color: #389e0d;
  }
  &.reject {
    background: #fff1f0;
    color: #cf1322;
  }
  &.return {
    background: #fffbe6;
    color: #d48806;
  }

  em {
    font-style: normal;
    font-weight: 600;
  }
}

.time {
  margin-top: 4px;
  font-size: 11px;
}

/* ---- 条件分支 ---- */
.branches {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.branch {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
  background: #fafafa;

  &.taken {
    border-color: #b7eb8f;
    background: #f6ffed;
  }

  &.skipped {
    opacity: 0.5;
  }
}

.branch-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.branch-name {
  font-weight: 600;
}

.branch-hint {
  color: rgba(0, 0, 0, 0.45);
  font-size: 11px;
}

.branch-nodes {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.branch-empty {
  margin-top: 2px;
  font-size: 11px;
  color: rgba(0, 0, 0, 0.45);
}

.sub-node {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;

  &.active .sub-name {
    color: #1677ff;
    font-weight: 600;
  }
}

.sub-status {
  color: rgba(0, 0, 0, 0.45);
  font-size: 11px;
}

/* ---- 并行组 ---- */
.members {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.member {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
  background: #fafafa;

  &.active {
    border-color: #91caff;
    background: #e6f4ff;
  }
}

.member-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.member-name {
  font-weight: 500;
}
</style>

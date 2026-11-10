<script setup lang="ts">
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'

import type { CanvasNode } from '@/components/flow-designer/canvas/layout'
import { NODE_TYPE_LABELS } from '@/types/flow'

const props = defineProps<{
  node: CanvasNode
  selected: boolean
  readonly: boolean
  dragging: boolean
  dropPosition: 'before' | 'after' | null
}>()

const emit = defineEmits<{
  select: [id: string]
  delete: [id: string]
  addAfter: [id: string]
  dragstart: [id: string, event: DragEvent]
  dragover: [id: string, event: DragEvent]
  drop: [id: string, event: DragEvent]
  dragend: []
}>()

const style = computed(() => ({
  left: `${props.node.x}px`,
  top: `${props.node.y}px`,
  width: `${props.node.width}px`,
  height: `${props.node.height}px`,
}))

const typeLabel = computed(() => NODE_TYPE_LABELS[props.node.kind])

function onSelect(): void {
  if (props.node.selectable) emit('select', props.node.id)
}

function onAddAfter(): void {
  if (!props.readonly) emit('addAfter', props.node.id)
}

function onDelete(): void {
  if (!props.readonly) emit('delete', props.node.id)
}

function onDragStart(event: DragEvent): void {
  if (!props.node.selectable || props.readonly) {
    event.preventDefault()
    return
  }
  emit('dragstart', props.node.id, event)
}
</script>

<template>
  <div
    class="canvas-node"
    :class="[
      `kind-${node.kind}`,
      {
        selected,
        dragging,
        terminal: !node.selectable,
        'drop-before': dropPosition === 'before',
        'drop-after': dropPosition === 'after',
      },
    ]"
    :style="style"
    :data-node-id="node.id"
    :draggable="node.selectable && !readonly"
    @click.stop="onSelect"
    @dragstart.stop="onDragStart"
    @dragover.stop.prevent="emit('dragover', node.id, $event)"
    @drop.stop.prevent="emit('drop', node.id, $event)"
    @dragend="emit('dragend')"
  >
    <div class="node-head">
      <span class="type-chip">{{ typeLabel }}</span>
      <span class="node-name" :title="node.name">{{ node.name }}</span>
      <span class="spacer" />
      <template v-if="node.selectable && !readonly">
        <button type="button" class="icon-btn" title="在后面插入节点" @click.stop="onAddAfter">
          <PlusOutlined />
        </button>
        <button type="button" class="icon-btn danger" title="删除节点" @click.stop="onDelete">
          <DeleteOutlined />
        </button>
      </template>
    </div>
    <div class="node-sub">{{ node.subtitle }}</div>
  </div>
</template>

<style scoped lang="scss">
.canvas-node {
  position: absolute;
  z-index: 2;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-left: 4px solid #1677ff;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  user-select: none;
  box-sizing: border-box;
  transition: box-shadow 0.15s, border-color 0.15s;

  &:hover {
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);
  }

  &.selected {
    border-color: #1677ff;
    box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.2);
  }

  &.dragging {
    opacity: 0.45;
  }

  &.drop-before::before,
  &.drop-after::after {
    content: '';
    position: absolute;
    left: 8px;
    right: 8px;
    height: 3px;
    border-radius: 2px;
    background: #1677ff;
  }

  &.drop-before::before {
    top: -10px;
  }

  &.drop-after::after {
    bottom: -10px;
  }

  &.kind-approval {
    border-left-color: #1677ff;
  }

  &.kind-fill {
    border-left-color: #722ed1;
  }

  &.kind-condition {
    border-left-color: #fa8c16;
  }

  &.kind-parallel {
    border-left-color: #13c2c2;
  }

  &.kind-cc {
    border-left-color: #8c8c8c;
  }

  &.terminal {
    border-left-color: #52c41a;
    background: #f6ffed;
    cursor: default;
    justify-content: center;
    align-items: center;
    padding: 8px 12px;
  }
}

.node-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.type-chip {
  flex: 0 0 auto;
  padding: 0 6px;
  border-radius: 3px;
  background: #f0f0f0;
  color: rgba(0, 0, 0, 0.6);
  font-size: 10px;
  line-height: 18px;
}

.node-name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}

.spacer {
  flex: 1;
}

.icon-btn {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: rgba(0, 0, 0, 0.45);
  cursor: pointer;
  font-size: 12px;
  line-height: 20px;

  &:hover {
    background: #f0f0f0;
    color: #1677ff;
  }

  &.danger:hover {
    color: #ff4d4f;
  }
}

.node-sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(0, 0, 0, 0.45);
  font-size: 11px;
}
</style>

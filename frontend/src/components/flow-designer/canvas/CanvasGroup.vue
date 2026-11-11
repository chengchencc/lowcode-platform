<script setup lang="ts">
import { computed } from 'vue'

import type { CanvasGroup, CanvasLane } from '@/components/flow-designer/canvas/layout'
import type { NodeContainer } from '@/components/flow-designer/definitionOps'

const props = defineProps<{ group: CanvasGroup }>()

const emit = defineEmits<{
  dragOverContainer: [container: NodeContainer, event: DragEvent]
  dropContainer: [container: NodeContainer, event: DragEvent]
  addNode: [container: NodeContainer]
}>()

const style = computed(() => ({
  left: `${props.group.x}px`,
  top: `${props.group.y}px`,
  width: `${props.group.width}px`,
  height: `${props.group.height}px`,
}))

function laneStyle(lane: CanvasLane): Record<string, string> {
  return {
    left: `${lane.x - props.group.x}px`,
    top: `${lane.y - props.group.y}px`,
    width: `${lane.width}px`,
    height: `${lane.height}px`,
  }
}

function onDragOver(container: NodeContainer, event: DragEvent): void {
  emit('dragOverContainer', container, event)
}

function onDrop(container: NodeContainer, event: DragEvent): void {
  emit('dropContainer', container, event)
}
</script>

<template>
  <div class="canvas-group" :class="`kind-${group.kind}`" :style="style">
    <div class="group-caption">{{ group.kind === 'condition' ? '条件分支' : '并行组' }}</div>
    <button
      v-if="group.kind === 'parallel'"
      type="button"
      class="group-add"
      title="添加并行成员"
      @click.stop="emit('addNode', { kind: 'parallel', parallelId: group.id })"
    >
      + 成员
    </button>
    <div
      v-for="lane in group.lanes"
      :key="lane.id"
      class="canvas-lane"
      :class="{ empty: lane.empty }"
      :style="laneStyle(lane)"
      @dragover.stop.prevent="onDragOver(lane.target, $event)"
      @drop.stop.prevent="onDrop(lane.target, $event)"
    >
      <div v-if="lane.kind === 'branch'" class="lane-label">{{ lane.label }}</div>
      <button
        v-if="lane.kind === 'branch'"
        type="button"
        class="lane-add"
        title="向此分支添加节点"
        @click.stop="emit('addNode', lane.target)"
      >
        +
      </button>
      <div v-if="lane.empty" class="lane-empty">
        {{ lane.kind === 'branch' ? '空分支：点右上角 + 添加，或拖入节点' : '空成员' }}
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.canvas-group {
  position: absolute;
  z-index: 0;
  border: 1px dashed #d9d9d9;
  border-radius: 10px;
  background: rgba(250, 250, 250, 0.7);
  box-sizing: border-box;

  &.kind-condition {
    border-color: #ffe7ba;
    background: rgba(255, 247, 230, 0.45);
  }

  &.kind-parallel {
    border-color: #b5f5ec;
    background: rgba(230, 255, 251, 0.45);
  }
}

.group-caption {
  position: absolute;
  top: 6px;
  left: 10px;
  color: rgba(0, 0, 0, 0.3);
  font-size: 10px;
  letter-spacing: 0.5px;
}

.group-add,
.lane-add {
  position: absolute;
  z-index: 1;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  color: rgba(0, 0, 0, 0.55);
  cursor: pointer;
  font-size: 11px;
  line-height: 18px;

  &:hover {
    border-color: #1677ff;
    color: #1677ff;
  }
}

.group-add {
  top: 3px;
  right: 8px;
  padding: 0 6px;
}

.lane-add {
  top: 3px;
  right: 4px;
  width: 20px;
  height: 20px;
  padding: 0;
}

.canvas-lane {
  position: absolute;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
  box-sizing: border-box;

  &.empty {
    border-style: dashed;
    background: rgba(255, 255, 255, 0.4);
  }
}

.lane-label {
  position: absolute;
  top: 4px;
  left: 8px;
  right: 28px;
  overflow: hidden;
  color: rgba(0, 0, 0, 0.55);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lane-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding-top: 20px;
  color: rgba(0, 0, 0, 0.3);
  font-size: 11px;
}
</style>

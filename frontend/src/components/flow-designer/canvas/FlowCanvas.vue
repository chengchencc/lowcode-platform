<script setup lang="ts">
import { ExpandOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed, nextTick, onMounted, ref } from 'vue'

import CanvasGroup from '@/components/flow-designer/canvas/CanvasGroup.vue'
import CanvasNode from '@/components/flow-designer/canvas/CanvasNode.vue'
import { buildCanvasLayout, type CanvasEdge } from '@/components/flow-designer/canvas/layout'
import {
  ADDABLE_NODES,
  addBranch,
  addParallelMember,
  findNode,
  insertAfter,
  insertIntoContainer,
  makeNode,
  moveNodeTo,
  removeNode,
  type AddableNodeType,
  type DropTarget,
  type NodeContainer,
} from '@/components/flow-designer/definitionOps'
import type { FlowDefinition } from '@/types/flow'

const props = defineProps<{
  definition: FlowDefinition
  selectedId: string | null
  readonly: boolean
}>()

const emit = defineEmits<{
  'update:selectedId': [id: string | null]
  change: []
}>()

const layout = computed(() => buildCanvasLayout(props.definition))
const selectedNode = computed(() =>
  props.selectedId ? findNode(props.definition, props.selectedId) : null,
)

// --------------------------------------------------------------------------- 缩放 / 平移

const viewport = ref<HTMLElement | null>(null)
const zoom = ref(1)
const pan = ref({ x: 0, y: 0 })

const zoomLabel = computed(() => `${Math.round(zoom.value * 100)}%`)

const contentStyle = computed(() => ({
  width: `${layout.value.width}px`,
  height: `${layout.value.height}px`,
  transform: `translate(${pan.value.x}px, ${pan.value.y}px) scale(${zoom.value})`,
}))

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function zoomBy(delta: number): void {
  zoom.value = clamp(Number((zoom.value + delta).toFixed(2)), 0.4, 1.6)
}

async function fitView(): Promise<void> {
  await nextTick()
  const el = viewport.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const sx = (rect.width - 32) / layout.value.width
  const sy = (rect.height - 32) / layout.value.height
  zoom.value = clamp(Math.min(1, sx, sy), 0.4, 1.6)
  pan.value = {
    x: (rect.width - layout.value.width * zoom.value) / 2,
    y: (rect.height - layout.value.height * zoom.value) / 2,
  }
}

onMounted(() => void fitView())

let panning = false
let panStart = { x: 0, y: 0, panX: 0, panY: 0 }

function startPan(event: PointerEvent): void {
  if (event.button !== 0) return
  const target = event.target
  // 必须用 Element 而不是 HTMLElement：点击 antd 图标时 target 是 <path>（SVGElement），
  // 用 HTMLElement 判断会漏掉，导致 viewport 捕获指针、按钮的 click 永远不会触发。
  if (target instanceof Element && target.closest('.canvas-node, .canvas-toolbar, button')) {
    return
  }
  panning = true
  panStart = {
    x: event.clientX,
    y: event.clientY,
    panX: pan.value.x,
    panY: pan.value.y,
  }
  const el = event.currentTarget as HTMLElement | null
  el?.setPointerCapture(event.pointerId)
}

function movePan(event: PointerEvent): void {
  if (!panning) return
  pan.value = {
    x: panStart.panX + event.clientX - panStart.x,
    y: panStart.panY + event.clientY - panStart.y,
  }
}

function endPan(event: PointerEvent): void {
  if (!panning) return
  panning = false
  const el = event.currentTarget as HTMLElement | null
  try {
    el?.releasePointerCapture(event.pointerId)
  } catch {
    // 指针已释放时忽略
  }
}

// --------------------------------------------------------------------------- 选择 / 删除 / 插入

function selectNode(id: string): void {
  emit('update:selectedId', id)
}

function onDelete(id: string): void {
  if (props.readonly) return
  const node = findNode(props.definition, id)
  if (!node) return
  if (!window.confirm(`删除节点「${node.name}」？其中配置的审批人与字段权限会一并移除。`)) return
  if (removeNode(props.definition, id)) {
    emit('change')
    emit('update:selectedId', props.definition.steps[0]?.id ?? null)
  }
}

type InsertTarget =
  | { kind: 'after'; id: string }
  | { kind: 'container'; container: NodeContainer }

const insertTarget = ref<InsertTarget | null>(null)
const insertOpen = computed({
  get: () => insertTarget.value !== null,
  set: (open: boolean) => {
    if (!open) insertTarget.value = null
  },
})

const insertTitle = computed(() =>
  insertTarget.value?.kind === 'container' ? '添加节点到分支/并行组' : '插入节点',
)

function openInsert(afterId: string): void {
  if (!props.readonly) insertTarget.value = { kind: 'after', id: afterId }
}

function openInsertInto(container: NodeContainer): void {
  if (!props.readonly) insertTarget.value = { kind: 'container', container }
}

function chooseInsert(type: AddableNodeType): void {
  const target = insertTarget.value
  if (!target) return
  const node = makeNode(props.definition, type)
  const inserted = target.kind === 'after'
    ? insertAfter(props.definition, target.id, node)
    : insertIntoContainer(props.definition, target.container, node)
  if (inserted) {
    emit('change')
    emit('update:selectedId', node.id)
  }
  insertTarget.value = null
}

// --------------------------------------------------------------------------- 拖拽

const draggingId = ref<string | null>(null)
const dropTarget = ref<DropTarget | null>(null)

function onNodeDragStart(id: string, event: DragEvent): void {
  if (props.readonly) return
  draggingId.value = id
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', id)
  }
}

function positionOf(event: DragEvent): 'before' | 'after' {
  const el = event.currentTarget as HTMLElement | null
  if (!el) {
    return dropTarget.value?.kind === 'sibling' ? dropTarget.value.position : 'after'
  }
  const rect = el.getBoundingClientRect()
  return event.clientY < rect.top + rect.height / 2 ? 'before' : 'after'
}

function onNodeDragOver(id: string, event: DragEvent): void {
  if (!draggingId.value || draggingId.value === id) return
  dropTarget.value = { kind: 'sibling', nodeId: id, position: positionOf(event) }
}

function onNodeDrop(id: string, event: DragEvent): void {
  if (!draggingId.value) return
  applyDrop({ kind: 'sibling', nodeId: id, position: positionOf(event) })
}

function onContainerDragOver(container: NodeContainer, _event?: DragEvent): void {
  if (!draggingId.value) return
  dropTarget.value = { kind: 'container', container }
}

function onContainerDrop(container: NodeContainer, _event?: DragEvent): void {
  applyDrop({ kind: 'container', container })
}

function applyDrop(target: DropTarget): void {
  const id = draggingId.value
  if (!id || props.readonly) return
  if (moveNodeTo(props.definition, id, target)) {
    emit('change')
    emit('update:selectedId', id)
  }
  clearDrag()
}

function clearDrag(): void {
  draggingId.value = null
  dropTarget.value = null
}

function dropPositionFor(id: string): 'before' | 'after' | null {
  const target = dropTarget.value
  if (target?.kind === 'sibling' && target.nodeId === id) return target.position
  return null
}

// --------------------------------------------------------------------------- 条件/并行快捷操作

function onAddBranch(): void {
  if (props.readonly || selectedNode.value?.type !== 'condition') return
  if (addBranch(props.definition, selectedNode.value.id)) emit('change')
}

function onAddMember(): void {
  if (props.readonly || selectedNode.value?.type !== 'parallel') return
  const node = makeNode(props.definition, 'approval')
  if (addParallelMember(props.definition, selectedNode.value.id, node)) {
    emit('change')
    emit('update:selectedId', node.id)
  }
}

function pathOf(edge: CanvasEdge): string {
  return edge.points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')
}
</script>

<template>
  <div class="flow-canvas">
    <div class="canvas-toolbar">
      <a-space size="small">
        <a-button size="small" title="缩小" @click="zoomBy(-0.1)">
          <template #icon><MinusOutlined /></template>
        </a-button>
        <span class="zoom-label">{{ zoomLabel }}</span>
        <a-button size="small" title="放大" @click="zoomBy(0.1)">
          <template #icon><PlusOutlined /></template>
        </a-button>
        <a-button size="small" @click="fitView">
          <template #icon><ExpandOutlined /></template>
          适配
        </a-button>
        <a-button size="small" :disabled="readonly" @click="openInsert('end')">
          <template #icon><PlusOutlined /></template>
          添加节点
        </a-button>
        <a-button
          v-if="selectedNode?.type === 'condition'"
          size="small"
          :disabled="readonly"
          @click="onAddBranch"
        >
          添加分支
        </a-button>
        <a-button
          v-else-if="selectedNode?.type === 'parallel'"
          size="small"
          :disabled="readonly"
          @click="onAddMember"
        >
          添加成员
        </a-button>
      </a-space>
    </div>

    <div
      ref="viewport"
      class="canvas-viewport"
      @pointerdown="startPan"
      @pointermove="movePan"
      @pointerup="endPan"
      @pointerleave="endPan"
    >
      <div class="canvas-content" :style="contentStyle">
        <CanvasGroup
          v-for="group in layout.groups"
          :key="group.id"
          :group="group"
          @drag-over-container="onContainerDragOver"
          @drop-container="onContainerDrop"
          @add-node="openInsertInto"
        />
        <svg class="canvas-edges" :width="layout.width" :height="layout.height">
          <path
            v-for="edge in layout.edges"
            :key="edge.id"
            :d="pathOf(edge)"
            :class="`edge-${edge.kind}`"
          />
        </svg>
        <CanvasNode
          v-for="node in layout.nodes"
          :key="node.id"
          :node="node"
          :selected="selectedId === node.id"
          :readonly="readonly"
          :dragging="draggingId === node.id"
          :drop-position="dropPositionFor(node.id)"
          @select="selectNode"
          @delete="onDelete"
          @add-after="openInsert"
          @dragstart="onNodeDragStart"
          @dragover="onNodeDragOver"
          @drop="onNodeDrop"
          @dragend="clearDrag"
        />
      </div>
    </div>

    <a-modal v-model:open="insertOpen" :title="insertTitle" :footer="null">
      <div class="insert-grid">
        <a-button
          v-for="item in ADDABLE_NODES"
          :key="item.type"
          block
          @click="chooseInsert(item.type)"
        >
          {{ item.label }}
        </a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.flow-canvas {
  position: relative;
  height: 640px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  overflow: hidden;
}

.canvas-toolbar {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 5;
  padding: 4px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.zoom-label {
  display: inline-block;
  min-width: 40px;
  color: rgba(0, 0, 0, 0.55);
  font-size: 12px;
  text-align: center;
}

.canvas-viewport {
  width: 100%;
  height: 100%;
  overflow: hidden;
  cursor: grab;
  background-color: #fafafa;
  background-image: radial-gradient(#e8e8e8 1px, transparent 1px);
  background-size: 16px 16px;

  &:active {
    cursor: grabbing;
  }
}

.canvas-content {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
}

.canvas-edges {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
  pointer-events: none;

  path {
    fill: none;
    stroke: #bfbfbf;
    stroke-width: 1.5;
  }

  .edge-branch {
    stroke: #d9d9d9;
    stroke-dasharray: 4 3;
  }
}

.insert-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
</style>

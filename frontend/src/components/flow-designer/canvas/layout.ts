/**
 * 流程画布的自动布局（纯函数，不依赖 DOM）。
 *
 * 主轴自上而下。条件分支与并行组成员横向分泳道，分支结束汇回主线。
 * 同一份定义多次布局必须得到完全一致的结果 —— 画布不做坐标持久化。
 */
import type { NodeContainer } from '@/components/flow-designer/definitionOps'
import type { ConditionNode, FlowDefinition, ParallelNode, StepNode } from '@/types/flow'
import { ASSIGNEE_MODE_LABELS } from '@/types/flow'

export const NODE_WIDTH = 220
export const NODE_HEIGHT = 76
export const TERMINAL_WIDTH = 160
export const TERMINAL_HEIGHT = 56
export const VERTICAL_GAP = 56
export const LANE_GAP = 40
export const CANVAS_PADDING = 48
export const GROUP_PADDING = 24
export const BRANCH_GAP = 36
export const BRANCH_HEADER_HEIGHT = 28
export const EMPTY_LANE_HEIGHT = 64
export const LANE_MIN_WIDTH = 180

export type CanvasNodeKind =
  | 'start' | 'approval' | 'fill' | 'parallel' | 'condition' | 'cc' | 'end'

export interface CanvasPoint {
  x: number
  y: number
}

export interface CanvasEdge {
  id: string
  kind: 'flow' | 'branch'
  points: CanvasPoint[]
}

export interface CanvasNode {
  id: string
  kind: CanvasNodeKind
  name: string
  subtitle: string
  x: number
  y: number
  width: number
  height: number
  parentId?: string
  selectable: boolean
}

export interface CanvasLane {
  id: string
  groupId: string
  kind: 'branch' | 'member'
  label: string
  x: number
  y: number
  width: number
  height: number
  empty: boolean
  target: NodeContainer
}

export interface CanvasGroup {
  id: string
  kind: 'condition' | 'parallel'
  x: number
  y: number
  width: number
  height: number
  lanes: CanvasLane[]
}

export interface CanvasLayout {
  width: number
  height: number
  nodes: CanvasNode[]
  edges: CanvasEdge[]
  groups: CanvasGroup[]
}

interface SubLayout {
  id: string
  width: number
  height: number
  entryX: number
  exitX: number
  nodes: CanvasNode[]
  edges: CanvasEdge[]
  groups: CanvasGroup[]
}

function makeSimpleLayout(input: {
  id: string
  kind: CanvasNodeKind
  name: string
  subtitle: string
  selectable: boolean
}): SubLayout {
  const terminal = input.kind === 'start' || input.kind === 'end'
  const width = terminal ? TERMINAL_WIDTH : NODE_WIDTH
  const height = terminal ? TERMINAL_HEIGHT : NODE_HEIGHT
  return {
    id: input.id,
    width,
    height,
    entryX: width / 2,
    exitX: width / 2,
    nodes: [{ ...input, x: 0, y: 0, width, height }],
    edges: [],
    groups: [],
  }
}

function subtitleOf(node: StepNode): string {
  switch (node.type) {
    case 'approval':
    case 'fill': {
      const mode = node.assignee?.mode ?? 'SINGLE'
      const sources = node.assignee?.sources?.length ?? 0
      return `${ASSIGNEE_MODE_LABELS[mode]}${sources ? ` · ${sources} 个来源` : ''}`
    }
    case 'cc':
      return '只读知会'
    case 'condition':
      return `${node.branches.length} 个分支`
    case 'parallel':
      return `${node.mode === 'all' ? '会签' : '或签'} · ${node.members.length} 个成员`
    default:
      return ''
  }
}

function orthogonalPoints(from: CanvasPoint, to: CanvasPoint): CanvasPoint[] {
  if (Math.abs(from.x - to.x) < 0.5) return [from, to]
  if (Math.abs(from.y - to.y) < 0.5) return [from, to]
  const midY = to.y > from.y ? from.y + (to.y - from.y) / 2 : from.y + 20
  return [from, { x: from.x, y: midY }, { x: to.x, y: midY }, to]
}

function makeEdge(
  id: string,
  from: CanvasPoint,
  to: CanvasPoint,
  kind: 'flow' | 'branch',
): CanvasEdge {
  return { id, kind, points: orthogonalPoints(from, to) }
}

function shiftGroup(group: CanvasGroup, dx: number, dy: number): CanvasGroup {
  return {
    ...group,
    x: group.x + dx,
    y: group.y + dy,
    lanes: group.lanes.map((lane) => ({ ...lane, x: lane.x + dx, y: lane.y + dy })),
  }
}

function shiftSub(sub: SubLayout, dx: number, dy: number): SubLayout {
  return {
    ...sub,
    nodes: sub.nodes.map((node) => ({ ...node, x: node.x + dx, y: node.y + dy })),
    edges: sub.edges.map((edge) => ({
      ...edge,
      points: edge.points.map((point) => ({ x: point.x + dx, y: point.y + dy })),
    })),
    groups: sub.groups.map((group) => shiftGroup(group, dx, dy)),
  }
}

function stackLayouts(layouts: SubLayout[], gap = VERTICAL_GAP): SubLayout {
  if (!layouts.length) {
    return { id: 'empty', width: 0, height: 0, entryX: 0, exitX: 0, nodes: [], edges: [], groups: [] }
  }
  const width = Math.max(...layouts.map((l) => l.width))
  const height = layouts.reduce((sum, l) => sum + l.height, 0) + gap * (layouts.length - 1)
  const nodes: CanvasNode[] = []
  const edges: CanvasEdge[] = []
  const groups: CanvasGroup[] = []
  let y = 0
  let previous: { layout: SubLayout; x: number } | null = null

  for (const layout of layouts) {
    const x = (width - layout.width) / 2
    const shifted = shiftSub(layout, x, y)
    nodes.push(...shifted.nodes)
    edges.push(...shifted.edges)
    groups.push(...shifted.groups)

    if (previous) {
      edges.push(makeEdge(
        `${previous.layout.id}->${layout.id}`,
        { x: previous.x + previous.layout.exitX, y: y - gap },
        { x: x + layout.entryX, y },
        'flow',
      ))
    }
    previous = { layout, x }
    y += layout.height + gap
  }

  const first = layouts[0]
  const last = layouts[layouts.length - 1]
  return {
    id: first.id,
    width,
    height,
    entryX: (width - first.width) / 2 + first.entryX,
    exitX: (width - last.width) / 2 + last.exitX,
    nodes,
    edges,
    groups,
  }
}

function layoutNode(node: StepNode): SubLayout {
  if (node.type === 'condition') return layoutCondition(node)
  if (node.type === 'parallel') return layoutParallel(node)
  return makeSimpleLayout({
    id: node.id,
    kind: node.type,
    name: node.name,
    subtitle: subtitleOf(node),
    selectable: true,
  })
}

function layoutCondition(node: ConditionNode): SubLayout {
  const header = makeSimpleLayout({
    id: node.id,
    kind: 'condition',
    name: node.name,
    subtitle: subtitleOf(node),
    selectable: true,
  })
  const branchLayouts = node.branches.map((branch) => ({
    branch,
    layout: stackLayouts(branch.steps.map(layoutNode)),
  }))
  const laneWidths = branchLayouts.map(({ layout }) => Math.max(layout.width, LANE_MIN_WIDTH))
  const laneHeights = branchLayouts.map(
    ({ layout }) => Math.max(layout.height, EMPTY_LANE_HEIGHT) + BRANCH_HEADER_HEIGHT,
  )
  const lanesWidth = laneWidths.reduce((a, b) => a + b, 0)
    + LANE_GAP * Math.max(branchLayouts.length - 1, 0)
  const groupWidth = Math.max(header.width, lanesWidth) + GROUP_PADDING * 2
  const headerX = (groupWidth - header.width) / 2
  const headerY = GROUP_PADDING
  const lanesStartX = (groupWidth - lanesWidth) / 2
  const laneY = GROUP_PADDING + header.height + BRANCH_GAP
  const lanesHeight = Math.max(...laneHeights, 0)
  const groupHeight = GROUP_PADDING + header.height + BRANCH_GAP + lanesHeight + GROUP_PADDING

  const lanes: CanvasLane[] = []
  const nodes: CanvasNode[] = []
  const edges: CanvasEdge[] = []
  const groups: CanvasGroup[] = []
  let laneX = lanesStartX

  branchLayouts.forEach(({ branch, layout }, index) => {
    const laneWidth = laneWidths[index]
    const laneHeight = laneHeights[index]
    const lane: CanvasLane = {
      id: `${node.id}:${branch.id}`,
      groupId: node.id,
      kind: 'branch',
      label: branch.name || (branch.when === null ? '否则' : branch.id),
      x: laneX,
      y: laneY,
      width: laneWidth,
      height: laneHeight,
      empty: layout.nodes.length === 0,
      target: { kind: 'branch', conditionId: node.id, branchId: branch.id },
    }
    lanes.push(lane)

    const contentX = laneX + (laneWidth - layout.width) / 2
    const contentY = laneY + BRANCH_HEADER_HEIGHT
    const shifted = shiftSub(layout, contentX, contentY)
    for (const child of shifted.nodes) {
      if (!child.parentId) child.parentId = node.id
    }
    nodes.push(...shifted.nodes)
    edges.push(...shifted.edges)
    groups.push(...shifted.groups)

    edges.push(makeEdge(
      `${node.id}->${lane.id}`,
      { x: headerX + header.width / 2, y: headerY + header.height },
      { x: laneX + laneWidth / 2, y: laneY },
      'branch',
    ))
    edges.push(makeEdge(
      `${lane.id}->${node.id}:exit`,
      { x: laneX + laneWidth / 2, y: laneY + laneHeight },
      { x: groupWidth / 2, y: groupHeight },
      'branch',
    ))
    laneX += laneWidth + LANE_GAP
  })

  groups.unshift({
    id: node.id,
    kind: 'condition',
    x: 0,
    y: 0,
    width: groupWidth,
    height: groupHeight,
    lanes,
  })
  const shiftedHeader = shiftSub(header, headerX, headerY)
  nodes.unshift(...shiftedHeader.nodes)

  return {
    id: node.id,
    width: groupWidth,
    height: groupHeight,
    entryX: headerX + header.width / 2,
    exitX: groupWidth / 2,
    nodes,
    edges,
    groups,
  }
}

function layoutParallel(node: ParallelNode): SubLayout {
  const header = makeSimpleLayout({
    id: node.id,
    kind: 'parallel',
    name: node.name,
    subtitle: subtitleOf(node),
    selectable: true,
  })
  const memberLayouts = node.members.map((member) => layoutNode(member))
  const laneWidths = memberLayouts.map((layout) => Math.max(layout.width, LANE_MIN_WIDTH))
  const laneHeights = memberLayouts.map((layout) => layout.height + 24)
  const lanesWidth = laneWidths.reduce((a, b) => a + b, 0)
    + LANE_GAP * Math.max(memberLayouts.length - 1, 0)
  const groupWidth = Math.max(header.width, lanesWidth) + GROUP_PADDING * 2
  const headerX = (groupWidth - header.width) / 2
  const headerY = GROUP_PADDING
  const lanesStartX = (groupWidth - lanesWidth) / 2
  const laneY = GROUP_PADDING + header.height + BRANCH_GAP
  const lanesHeight = Math.max(...laneHeights, 0)
  const groupHeight = GROUP_PADDING + header.height + BRANCH_GAP + lanesHeight + GROUP_PADDING

  const lanes: CanvasLane[] = []
  const nodes: CanvasNode[] = []
  const edges: CanvasEdge[] = []
  const groups: CanvasGroup[] = []
  let laneX = lanesStartX

  memberLayouts.forEach((layout, index) => {
    const member = node.members[index]
    const laneWidth = laneWidths[index]
    const laneHeight = laneHeights[index]
    const lane: CanvasLane = {
      id: `${node.id}:${member.id}`,
      groupId: node.id,
      kind: 'member',
      label: member.name,
      x: laneX,
      y: laneY,
      width: laneWidth,
      height: laneHeight,
      empty: false,
      target: { kind: 'parallel', parallelId: node.id },
    }
    lanes.push(lane)

    const shifted = shiftSub(layout, laneX + (laneWidth - layout.width) / 2, laneY + 12)
    for (const child of shifted.nodes) {
      if (!child.parentId) child.parentId = node.id
    }
    nodes.push(...shifted.nodes)
    edges.push(...shifted.edges)
    groups.push(...shifted.groups)

    edges.push(makeEdge(
      `${node.id}->${lane.id}`,
      { x: headerX + header.width / 2, y: headerY + header.height },
      { x: laneX + laneWidth / 2, y: laneY },
      'branch',
    ))
    edges.push(makeEdge(
      `${lane.id}->${node.id}:exit`,
      { x: laneX + laneWidth / 2, y: laneY + laneHeight },
      { x: groupWidth / 2, y: groupHeight },
      'branch',
    ))
    laneX += laneWidth + LANE_GAP
  })

  groups.unshift({
    id: node.id,
    kind: 'parallel',
    x: 0,
    y: 0,
    width: groupWidth,
    height: groupHeight,
    lanes,
  })
  const shiftedHeader = shiftSub(header, headerX, headerY)
  nodes.unshift(...shiftedHeader.nodes)

  return {
    id: node.id,
    width: groupWidth,
    height: groupHeight,
    entryX: headerX + header.width / 2,
    exitX: groupWidth / 2,
    nodes,
    edges,
    groups,
  }
}

export function buildCanvasLayout(definition: FlowDefinition): CanvasLayout {
  const start = makeSimpleLayout({
    id: definition.start.id,
    kind: 'start',
    name: definition.start.name,
    subtitle: '发起人填写',
    selectable: false,
  })
  const end = makeSimpleLayout({
    id: definition.end.id,
    kind: 'end',
    name: definition.end.name,
    subtitle: '流程结束',
    selectable: false,
  })
  const root = stackLayouts([start, ...definition.steps.map(layoutNode), end])
  const shifted = shiftSub(root, CANVAS_PADDING, CANVAS_PADDING)
  return {
    width: root.width + CANVAS_PADDING * 2,
    height: root.height + CANVAS_PADDING * 2,
    nodes: shifted.nodes,
    edges: shifted.edges,
    groups: shifted.groups,
  }
}

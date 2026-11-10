/**
 * 流程定义的结构化操作与节点工厂。
 *
 * 画布与清单共用。所有函数只修改传入的 definition，不碰 DOM、不发请求，
 * 这样布局、拖拽、清单按钮都走同一套结构不变式。
 */
import type {
  ApprovalNode,
  Branch,
  CcNode,
  ConditionNode,
  FillNode,
  FlowDefinition,
  ParallelNode,
  StepNode,
} from '@/types/flow'

export type AddableNodeType = 'approval' | 'fill' | 'cc' | 'condition' | 'parallel'

export type NodeContainer =
  | { kind: 'root' }
  | { kind: 'branch'; conditionId: string; branchId: string }
  | { kind: 'parallel'; parallelId: string }

export interface NodeLocation {
  node: StepNode
  list: StepNode[]
  index: number
  container: NodeContainer
}

export type DropTarget =
  | { kind: 'sibling'; nodeId: string; position: 'before' | 'after' }
  | { kind: 'container'; container: NodeContainer }

/** 所有节点 id（不含 start/end；它们固定且不可删除）。 */
export function collectNodeIds(definition: FlowDefinition): Set<string> {
  const used = new Set<string>()
  const walk = (steps: StepNode[]): void => {
    for (const step of steps) {
      used.add(step.id)
      if (step.type === 'condition') {
        for (const branch of step.branches) walk(branch.steps)
      } else if (step.type === 'parallel') {
        walk(step.members as StepNode[])
      }
    }
  }
  walk(definition.steps)
  return used
}

function sameContainer(a: NodeContainer, b: NodeContainer): boolean {
  if (a.kind !== b.kind) return false
  if (a.kind === 'root') return true
  if (a.kind === 'parallel' && b.kind === 'parallel') return a.parallelId === b.parallelId
  if (a.kind === 'branch' && b.kind === 'branch') {
    return a.conditionId === b.conditionId && a.branchId === b.branchId
  }
  return false
}

function isInsideNode(root: StepNode, targetId: string): boolean {
  if (root.id === targetId) return true
  if (root.type === 'condition') {
    for (const branch of root.branches) {
      for (const step of branch.steps) {
        if (isInsideNode(step, targetId)) return true
      }
    }
  } else if (root.type === 'parallel') {
    for (const member of root.members) {
      if (isInsideNode(member, targetId)) return true
    }
  }
  return false
}

function canContain(container: NodeContainer, node: StepNode): boolean {
  if (container.kind === 'root') return true
  if (container.kind === 'parallel') return node.type === 'approval' || node.type === 'fill'
  // 与现有配置器一致：条件分支内不直接放并行组
  return node.type !== 'parallel'
}

export function containerList(
  definition: FlowDefinition,
  container: NodeContainer,
): StepNode[] | null {
  if (container.kind === 'root') return definition.steps
  if (container.kind === 'parallel') {
    const node = findNode(definition, container.parallelId)
    return node?.type === 'parallel' ? (node.members as StepNode[]) : null
  }
  const condition = findNode(definition, container.conditionId)
  if (condition?.type !== 'condition') return null
  return condition.branches.find((b) => b.id === container.branchId)?.steps ?? null
}

export function findLocation(definition: FlowDefinition, id: string): NodeLocation | null {
  const walk = (steps: StepNode[], container: NodeContainer): NodeLocation | null => {
    for (let index = 0; index < steps.length; index += 1) {
      const node = steps[index]
      if (node.id === id) return { node, list: steps, index, container }
      if (node.type === 'condition') {
        for (const branch of node.branches) {
          const hit = walk(branch.steps, {
            kind: 'branch', conditionId: node.id, branchId: branch.id,
          })
          if (hit) return hit
        }
      }
      if (node.type === 'parallel') {
        const hit = walk(node.members as StepNode[], { kind: 'parallel', parallelId: node.id })
        if (hit) return hit
      }
    }
    return null
  }
  return walk(definition.steps, { kind: 'root' })
}

export function findNode(definition: FlowDefinition, id: string): StepNode | null {
  return findLocation(definition, id)?.node ?? null
}

export function removeNode(definition: FlowDefinition, id: string): boolean {
  const location = findLocation(definition, id)
  if (!location) return false
  location.list.splice(location.index, 1)
  return true
}

export function moveWithinSiblings(
  definition: FlowDefinition,
  id: string,
  targetIndex: number,
): boolean {
  const location = findLocation(definition, id)
  if (!location) return false
  const clamped = Math.max(0, Math.min(targetIndex, location.list.length - 1))
  if (clamped === location.index) return false
  const [node] = location.list.splice(location.index, 1)
  location.list.splice(clamped, 0, node)
  return true
}

export function insertAfter(
  definition: FlowDefinition,
  afterId: string,
  node: StepNode,
): boolean {
  if (afterId === 'start') {
    definition.steps.splice(0, 0, node)
    return true
  }
  if (afterId === 'end') {
    definition.steps.push(node)
    return true
  }
  const location = findLocation(definition, afterId)
  if (!location) return false
  location.list.splice(location.index + 1, 0, node)
  return true
}

/** 把新节点直接追加到根 / 条件分支 / 并行组的末尾。 */
export function insertIntoContainer(
  definition: FlowDefinition,
  container: NodeContainer,
  node: StepNode,
): boolean {
  const list = containerList(definition, container)
  if (!list) return false
  if (!canContain(container, node)) return false
  if (collectNodeIds(definition).has(node.id)) return false
  list.push(node)
  return true
}

export function addBranch(definition: FlowDefinition, conditionId: string): Branch | null {
  const node = findNode(definition, conditionId)
  if (node?.type !== 'condition') return null
  const used = new Set(node.branches.map((b) => b.id))
  let n = 1
  while (used.has(`b${n}`)) n += 1
  const branch: Branch = {
    id: `b${n}`,
    name: `分支 ${n}`,
    when: { op: 'and', conditions: [] },
    steps: [],
  }
  const elseIndex = node.branches.findIndex((b) => b.when === null)
  if (elseIndex >= 0) node.branches.splice(elseIndex, 0, branch)
  else node.branches.push(branch)
  return branch
}

export function removeBranch(
  definition: FlowDefinition,
  conditionId: string,
  branchId: string,
): boolean {
  const node = findNode(definition, conditionId)
  if (node?.type !== 'condition') return false
  const index = node.branches.findIndex((b) => b.id === branchId)
  if (index < 0) return false
  node.branches.splice(index, 1)
  return true
}

export function addParallelMember(
  definition: FlowDefinition,
  parallelId: string,
  node: StepNode,
): boolean {
  const parallel = findNode(definition, parallelId)
  if (parallel?.type !== 'parallel') return false
  if (node.type !== 'approval' && node.type !== 'fill') return false
  if (collectNodeIds(definition).has(node.id)) return false
  parallel.members.push(node)
  return true
}

export function moveNodeTo(
  definition: FlowDefinition,
  id: string,
  target: DropTarget,
): boolean {
  const source = findLocation(definition, id)
  if (!source) return false

  if (target.kind === 'sibling') {
    if (target.nodeId === id) return false
    const dest = findLocation(definition, target.nodeId)
    if (!dest) return false
    if (isInsideNode(source.node, target.nodeId)) return false
    if (!sameContainer(source.container, dest.container) && !canContain(dest.container, source.node)) {
      return false
    }

    const sameList = source.list === dest.list
    const destIndex = dest.index
    source.list.splice(source.index, 1)
    let insertIndex = sameList
      ? (source.index < destIndex ? destIndex - 1 : destIndex)
      : destIndex
    if (target.position === 'after') insertIndex += 1
    dest.list.splice(insertIndex, 0, source.node)
    return true
  }

  const destList = containerList(definition, target.container)
  if (!destList) return false
  if (!canContain(target.container, source.node)) return false
  if (target.container.kind === 'branch' && isInsideNode(source.node, target.container.conditionId)) {
    return false
  }
  if (target.container.kind === 'parallel' && isInsideNode(source.node, target.container.parallelId)) {
    return false
  }
  source.list.splice(source.index, 1)
  destList.push(source.node)
  return true
}

function nextId(used: Set<string>, prefix: string): string {
  if (!used.has(prefix)) {
    used.add(prefix)
    return prefix
  }
  let n = 2
  while (used.has(`${prefix}${n}`)) n += 1
  const id = `${prefix}${n}`
  used.add(id)
  return id
}

export function makeApprovalNode(used: Set<string>): ApprovalNode {
  const id = nextId(used, 's')
  return {
    id, type: 'approval', name: `审批节点 ${id}`,
    assignee: { mode: 'SINGLE', sources: [] },
    reject_policy: 'reject_to_initiator',
    return_targets: null,
    timeout_hours: null,
    opinion_required: false,
    attachment_required: false,
    fields_permission: {
      base: 'readonly', partitions: {}, overrides: {}, conditional_overrides: [],
    },
  }
}

export function makeFillNode(used: Set<string>): FillNode {
  const id = nextId(used, 'f')
  return {
    id, type: 'fill', name: `填写节点 ${id}`,
    assignee: { mode: 'SINGLE', sources: [] },
    return_targets: null,
    timeout_hours: null,
    fields_permission: {
      base: 'hidden', partitions: {}, overrides: {}, conditional_overrides: [],
    },
  }
}

export function makeCcNode(used: Set<string>): CcNode {
  const id = nextId(used, 'cc')
  return {
    id, type: 'cc', name: `抄送 ${id}`,
    cc_to: { mode: 'SINGLE', sources: [] },
    allow_read: true,
  }
}

export function makeConditionNode(used: Set<string>): ConditionNode {
  const id = nextId(used, 'c')
  return {
    id, type: 'condition', name: `条件分支 ${id}`,
    branches: [
      { id: 'b1', name: '分支 1', when: { op: 'and', conditions: [] }, steps: [] },
      { id: 'else', name: '否则', when: null, steps: [] },
    ],
  }
}

export function makeParallelNode(used: Set<string>): ParallelNode {
  const id = nextId(used, 'p')
  return {
    id, type: 'parallel', name: `并行组 ${id}`, mode: 'all',
    members: [makeApprovalNode(used), makeApprovalNode(used)],
  }
}

export function makeNode(definition: FlowDefinition, type: AddableNodeType): StepNode {
  const used = collectNodeIds(definition)
  switch (type) {
    case 'approval': return makeApprovalNode(used)
    case 'fill': return makeFillNode(used)
    case 'cc': return makeCcNode(used)
    case 'condition': return makeConditionNode(used)
    case 'parallel': return makeParallelNode(used)
  }
}

export const ADDABLE_NODES: Array<{ type: AddableNodeType; label: string }> = [
  { type: 'approval', label: '审批节点' },
  { type: 'fill', label: '填写节点' },
  { type: 'cc', label: '抄送节点' },
  { type: 'condition', label: '条件分支' },
  { type: 'parallel', label: '并行组' },
]

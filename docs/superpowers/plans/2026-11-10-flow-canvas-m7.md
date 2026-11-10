# FlowForm M7 流程可视化画布 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有流程定义 JSON 上增加自动布局画布，支持节点增删、同级拖拽排序、拖入条件分支/并行组，并与清单视图共用同一份数据与保存/发布路径。

**Architecture:** 新增三层：`definitionOps.ts` 负责纯结构操作与节点工厂；`canvas/layout.ts` 负责确定性自动布局；`FlowCanvas.vue` 负责渲染、缩放/平移与拖拽事件。`FlowDesignerView.vue` 只增加视图切换与接线，属性面板、保存、发布、引擎全部复用。

**Tech Stack:** Vue 3 `<script setup>` + TypeScript + Ant Design Vue 4 + Vitest + happy-dom。不引入图库依赖。

---

## File Structure

```
frontend/src/components/flow-designer/
├─ definitionOps.ts              # 新增：查找/删除/移动/插入/分支/成员/节点工厂
├─ definitionOps.spec.ts        # 新增：结构操作单测
├─ canvas/
│  ├─ layout.ts                  # 新增：FlowDefinition -> CanvasLayout 纯函数
│  ├─ layout.spec.ts             # 新增：布局单测
│  ├─ CanvasNode.vue             # 新增：节点卡片
│  ├─ CanvasGroup.vue            # 新增：条件/并行容器与泳道
│  ├─ FlowCanvas.vue             # 新增：画布容器（缩放/平移/拖拽/插入弹窗）
│  └─ FlowCanvas.spec.ts         # 新增：画布组件测试
frontend/src/views/admin/flow/
└─ FlowDesignerView.vue          # 修改：视图切换 + 接线
docs/PHASE2-DESIGN.md             # 修改：M7 状态
docs/TECH-DESIGN.md               # 修改：M7 状态与测试项
README.md                         # 修改：里程碑表
```

---

## Task 1: 抽出流程定义操作与节点工厂

**Files:**
- Create: `frontend/src/components/flow-designer/definitionOps.ts`
- Test: `frontend/src/components/flow-designer/definitionOps.spec.ts`

- [ ] **Step 1: 写失败测试**

创建 `definitionOps.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'

import {
  addBranch,
  addParallelMember,
  collectNodeIds,
  findLocation,
  findNode,
  insertAfter,
  makeNode,
  moveNodeTo,
  moveWithinSiblings,
  removeNode,
} from '@/components/flow-designer/definitionOps'
import type { FlowDefinition, StepNode } from '@/types/flow'

function approval(id: string, name = id): StepNode {
  return {
    id, type: 'approval', name,
    assignee: { mode: 'SINGLE', sources: [] },
    reject_policy: 'reject_to_initiator',
    return_targets: null,
    timeout_hours: null,
    opinion_required: false,
    attachment_required: false,
    fields_permission: { base: 'readonly', partitions: {}, overrides: {}, conditional_overrides: [] },
  }
}

function fill(id: string, name = id): StepNode {
  return {
    id, type: 'fill', name,
    assignee: { mode: 'SINGLE', sources: [] },
    return_targets: null,
    timeout_hours: null,
    fields_permission: { base: 'hidden', partitions: {}, overrides: {}, conditional_overrides: [] },
  }
}

function definition(): FlowDefinition {
  return {
    model_version: 1,
    start: { id: 'start', type: 'start', name: '发起', fields_permission: null },
    steps: [
      approval('s1'),
      {
        id: 'c1', type: 'condition', name: '条件',
        branches: [
          { id: 'b1', name: '分支 1', when: { op: 'and', conditions: [] }, steps: [fill('s2')] },
          { id: 'else', name: '否则', when: null, steps: [] },
        ],
      },
      {
        id: 'p1', type: 'parallel', name: '并行', mode: 'all',
        members: [approval('m1'), approval('m2')],
      },
      {
        id: 'cc1', type: 'cc', name: '抄送',
        cc_to: { mode: 'SINGLE', sources: [] }, allow_read: true,
      },
    ],
    end: { id: 'end', type: 'end', name: '结束' },
  }
}

describe('definitionOps', () => {
  it('能定位根、分支与并行组里的节点', () => {
    const def = definition()
    expect(findLocation(def, 's1')?.container).toEqual({ kind: 'root' })
    expect(findLocation(def, 's2')?.container).toEqual({
      kind: 'branch', conditionId: 'c1', branchId: 'b1',
    })
    expect(findLocation(def, 'm1')?.container).toEqual({ kind: 'parallel', parallelId: 'p1' })
    expect(findNode(def, 'missing')).toBeNull()
  })

  it('删除节点只影响所在容器；删除容器会级联移除子树', () => {
    const a = definition()
    expect(removeNode(a, 's2')).toBe(true)
    expect(findNode(a, 's2')).toBeNull()
    expect(findNode(a, 's1')).not.toBeNull()

    const b = definition()
    expect(removeNode(b, 'c1')).toBe(true)
    expect(findNode(b, 's2')).toBeNull()
    expect(b.steps.map((s) => s.id)).toEqual(['s1', 'p1', 'cc1'])
  })

  it('同级移动与插入保持层级不变', () => {
    const def = definition()
    expect(moveWithinSiblings(def, 'p1', 0)).toBe(true)
    expect(def.steps.map((s) => s.id)).toEqual(['p1', 's1', 'c1', 'cc1'])

    expect(insertAfter(def, 'start', approval('s0'))).toBe(true)
    expect(def.steps[0].id).toBe('s0')
    expect(insertAfter(def, 'end', approval('s9'))).toBe(true)
    expect(def.steps.at(-1)?.id).toBe('s9')
  })

  it('新增分支插在 else 之前，且 id 不重复', () => {
    const def = definition()
    const branch = addBranch(def, 'c1')
    expect(branch?.id).toBe('b2')
    const condition = findNode(def, 'c1')
    expect(condition?.type).toBe('condition')
    if (condition?.type === 'condition') {
      expect(condition.branches.map((b) => b.id)).toEqual(['b1', 'b2', 'else'])
    }
  })

  it('并行组只接受审批/填写成员', () => {
    const def = definition()
    expect(addParallelMember(def, 'p1', approval('m3'))).toBe(true)
    expect(addParallelMember(def, 'p1', fill('m4'))).toBe(true)
    expect(addParallelMember(def, 'p1', makeNode(def, 'condition'))).toBe(false)
  })

  it('拖拽到节点前后，可在同级列表内重排', () => {
    const def = definition()
    expect(moveNodeTo(def, 'cc1', { kind: 'sibling', nodeId: 's1', position: 'before' })).toBe(true)
    expect(def.steps.map((s) => s.id)).toEqual(['cc1', 's1', 'c1', 'p1'])

    expect(moveNodeTo(def, 'cc1', { kind: 'sibling', nodeId: 'p1', position: 'after' })).toBe(true)
    expect(def.steps.map((s) => s.id)).toEqual(['s1', 'c1', 'p1', 'cc1'])
  })

  it('拖入条件分支与并行组；禁止把容器拖进自己的子树', () => {
    const def = definition()
    expect(moveNodeTo(def, 's1', {
      kind: 'container', container: { kind: 'branch', conditionId: 'c1', branchId: 'b1' },
    })).toBe(true)
    if (findNode(def, 'c1')?.type === 'condition') {
      expect(findNode(def, 'c1')!.type === 'condition'
        && (findNode(def, 'c1') as Extract<StepNode, { type: 'condition' }>).branches[0].steps.map((s) => s.id))
        .toEqual(['s2', 's1'])
    }

    // 审批节点可以进入并行组
    expect(moveNodeTo(def, 's1', {
      kind: 'container', container: { kind: 'parallel', parallelId: 'p1' },
    })).toBe(true)
    expect(def.steps.map((s) => s.id)).toEqual(['c1', 'p1', 'cc1'])
    expect(findNode(def, 'p1')?.type).toBe('parallel')
    if (findNode(def, 'p1')?.type === 'parallel') {
      expect((findNode(def, 'p1') as Extract<StepNode, { type: 'parallel' }>).members.map((m) => m.id))
        .toEqual(['m1', 'm2', 's1'])
    }
  })

  it('容器不能进入自己的子树', () => {
    const def = definition()
    expect(moveNodeTo(def, 'c1', {
      kind: 'container', container: { kind: 'branch', conditionId: 'c1', branchId: 'b1' },
    })).toBe(false)
  })

  it('节点工厂生成唯一 id，并覆盖并行组两个成员', () => {
    const def = definition()
    const used = collectNodeIds(def)
    expect(used.has('s1')).toBe(true)

    const condition = makeNode(def, 'condition')
    expect(condition.type).toBe('condition')
    expect(used.has(condition.id)).toBe(false)

    const parallel = makeNode(def, 'parallel')
    expect(parallel.type).toBe('parallel')
    if (parallel.type === 'parallel') {
      expect(parallel.members.length).toBe(2)
      expect(parallel.members[0].id).not.toBe(parallel.members[1].id)
    }
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/flow-designer/definitionOps.spec.ts`

Expected: FAIL，提示模块 `definitionOps` 不存在。

- [ ] **Step 3: 实现 definitionOps**

创建 `frontend/src/components/flow-designer/definitionOps.ts`：

```ts
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/components/flow-designer/definitionOps.spec.ts`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/flow-designer/definitionOps.ts frontend/src/components/flow-designer/definitionOps.spec.ts
git commit -m "feat(M7): 抽出流程定义操作与节点工厂"
```

---

## Task 2: 画布自动布局纯函数

**Files:**
- Create: `frontend/src/components/flow-designer/canvas/layout.ts`
- Test: `frontend/src/components/flow-designer/canvas/layout.spec.ts`

- [ ] **Step 1: 写失败测试**

创建 `layout.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'

import { buildCanvasLayout } from '@/components/flow-designer/canvas/layout'
import type { FlowDefinition, StepNode } from '@/types/flow'

function approval(id: string): StepNode {
  return {
    id, type: 'approval', name: id,
    assignee: { mode: 'SINGLE', sources: [] },
    reject_policy: 'reject_to_initiator',
    return_targets: null, timeout_hours: null,
    opinion_required: false, attachment_required: false,
    fields_permission: { base: 'readonly', partitions: {}, overrides: {}, conditional_overrides: [] },
  }
}

function def(steps: StepNode[]): FlowDefinition {
  return {
    model_version: 1,
    start: { id: 'start', type: 'start', name: '发起', fields_permission: null },
    steps,
    end: { id: 'end', type: 'end', name: '结束' },
  }
}

describe('buildCanvasLayout', () => {
  it('顺序流程从上到下排列，并连接 start/end', () => {
    const layout = buildCanvasLayout(def([approval('s1'), approval('s2')]))
    expect(layout.nodes.map((n) => n.id)).toEqual(['start', 's1', 's2', 'end'])
    expect(layout.edges.length).toBe(3)
    const ys = ['start', 's1', 's2', 'end'].map(
      (id) => layout.nodes.find((n) => n.id === id)!.y,
    )
    expect(ys).toEqual([...ys].sort((a, b) => a - b))
  })

  it('空流程也有 start -> end 一条边', () => {
    const layout = buildCanvasLayout(def([]))
    expect(layout.edges.length).toBe(1)
    expect(layout.edges[0].points.length).toBeGreaterThanOrEqual(2)
  })

  it('条件分支生成一个组与两条泳道，记录分支目标', () => {
    const layout = buildCanvasLayout(def([
      {
        id: 'c1', type: 'condition', name: '分流',
        branches: [
          { id: 'b1', name: '大额', when: { op: 'and', conditions: [] }, steps: [approval('s1')] },
          { id: 'else', name: '否则', when: null, steps: [] },
        ],
      },
    ]))
    const group = layout.groups.find((g) => g.id === 'c1')
    expect(group?.kind).toBe('condition')
    expect(group?.lanes.length).toBe(2)
    expect(group?.lanes[0].target).toEqual({ kind: 'branch', conditionId: 'c1', branchId: 'b1' })
    expect(group?.lanes[1].empty).toBe(true)
    expect(layout.nodes.find((n) => n.id === 's1')?.parentId).toBe('c1')
  })

  it('并行组生成成员泳道，成员记录父组', () => {
    const layout = buildCanvasLayout(def([
      {
        id: 'p1', type: 'parallel', name: '会签', mode: 'all',
        members: [approval('m1'), approval('m2')],
      },
    ]))
    const group = layout.groups.find((g) => g.id === 'p1')
    expect(group?.kind).toBe('parallel')
    expect(group?.lanes.length).toBe(2)
    expect(layout.nodes.find((n) => n.id === 'm1')?.parentId).toBe('p1')
  })

  it('嵌套条件会生成两个组，内层位于外层泳道内', () => {
    const layout = buildCanvasLayout(def([
      {
        id: 'c1', type: 'condition', name: '外层',
        branches: [{
          id: 'b1', name: '分支', when: { op: 'and', conditions: [] },
          steps: [{
            id: 'c2', type: 'condition', name: '内层',
            branches: [
              { id: 'b1', name: '内层分支', when: { op: 'and', conditions: [] }, steps: [approval('s1')] },
              { id: 'else', name: '否则', when: null, steps: [] },
            ],
          }],
        }],
      },
    ]))
    const outer = layout.groups.find((g) => g.id === 'c1')!
    const inner = layout.groups.find((g) => g.id === 'c2')!
    expect(outer).toBeTruthy()
    expect(inner).toBeTruthy()
    expect(inner.x).toBeGreaterThan(outer.x)
    expect(inner.y).toBeGreaterThan(outer.y)
    expect(inner.x + inner.width).toBeLessThanOrEqual(outer.x + outer.width)
    expect(inner.y + inner.height).toBeLessThanOrEqual(outer.y + outer.height)
  })

  it('布局是确定性的', () => {
    const input = def([approval('s1')])
    expect(buildCanvasLayout(input)).toEqual(buildCanvasLayout(input))
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/flow-designer/canvas/layout.spec.ts`

Expected: FAIL，提示模块 `layout` 不存在。

- [ ] **Step 3: 实现 layout.ts**

创建 `frontend/src/components/flow-designer/canvas/layout.ts`：

```ts
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
  const laneHeights = branchLayouts.map(({ layout }) => Math.max(layout.height, EMPTY_LANE_HEIGHT) + BRANCH_HEADER_HEIGHT)
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/components/flow-designer/canvas/layout.spec.ts`

Expected: PASS。若嵌套组坐标断言失败，检查 `shiftSub` 是否同时平移了 lanes 与 groups。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/flow-designer/canvas/layout.ts frontend/src/components/flow-designer/canvas/layout.spec.ts
git commit -m "feat(M7): 流程画布自动布局纯函数"
```

---

## Task 3: 画布节点与分组组件

**Files:**
- Create: `frontend/src/components/flow-designer/canvas/CanvasNode.vue`
- Create: `frontend/src/components/flow-designer/canvas/CanvasGroup.vue`

- [ ] **Step 1: 创建 CanvasNode.vue**

```vue
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
    @click.stop="node.selectable && emit('select', node.id)"
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
        <button type="button" class="icon-btn" title="在后面插入节点" @click.stop="emit('addAfter', node.id)">
          <PlusOutlined />
        </button>
        <button type="button" class="icon-btn danger" title="删除节点" @click.stop="emit('delete', node.id)">
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
```

- [ ] **Step 2: 创建 CanvasGroup.vue**

```vue
<script setup lang="ts">
import { computed } from 'vue'

import type { NodeContainer } from '@/components/flow-designer/definitionOps'
import type { CanvasGroup } from '@/components/flow-designer/canvas/layout'

const props = defineProps<{ group: CanvasGroup }>()

const emit = defineEmits<{
  dragOverContainer: [container: NodeContainer, event: DragEvent]
  dropContainer: [container: NodeContainer, event: DragEvent]
}>()

const style = computed(() => ({
  left: `${props.group.x}px`,
  top: `${props.group.y}px`,
  width: `${props.group.width}px`,
  height: `${props.group.height}px`,
}))

function laneStyle(lane: CanvasGroup['lanes'][number]): Record<string, string> {
  return {
    left: `${lane.x - props.group.x}px`,
    top: `${lane.y - props.group.y}px`,
    width: `${lane.width}px`,
    height: `${lane.height}px`,
  }
}
</script>

<template>
  <div class="canvas-group" :class="`kind-${group.kind}`" :style="style">
    <div class="group-caption">{{ group.kind === 'condition' ? '条件分支' : '并行组' }}</div>
    <div
      v-for="lane in group.lanes"
      :key="lane.id"
      class="canvas-lane"
      :class="{ empty: lane.empty }"
      :style="laneStyle(lane)"
      @dragover.stop.prevent="emit('dragOverContainer', lane.target, $event)"
      @drop.stop.prevent="emit('dropContainer', lane.target, $event)"
    >
      <div v-if="lane.kind === 'branch'" class="lane-label">{{ lane.label }}</div>
      <div v-if="lane.empty" class="lane-empty">
        {{ lane.kind === 'branch' ? '空分支，可拖入节点' : '空成员' }}
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
  right: 8px;
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
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npm run typecheck`

Expected: PASS（若 `CanvasNode` 与 Vue 的 `Node` 类型重名，组件内 import 已显式命名为 `CanvasNode`，没问题）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/flow-designer/canvas/CanvasNode.vue frontend/src/components/flow-designer/canvas/CanvasGroup.vue
git commit -m "feat(M7): 画布节点与分组组件"
```

---

## Task 4: 画布容器 FlowCanvas.vue

**Files:**
- Create: `frontend/src/components/flow-designer/canvas/FlowCanvas.vue`

- [ ] **Step 1: 写组件**

创建 `frontend/src/components/flow-designer/canvas/FlowCanvas.vue`：

```vue
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

const contentStyle = computed(() => ({
  width: `${layout.value.width}px`,
  height: `${layout.value.height}px`,
  transform: `translate(${pan.value.x}px, ${pan.value.y}px) scale(${zoom.value})`,
}))

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

const zoomLabel = computed(() => `${Math.round(zoom.value * 100)}%`)

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
  const target = event.target as HTMLElement
  if (target.closest('.canvas-node, .canvas-toolbar, button')) return
  panning = true
  panStart = {
    x: event.clientX,
    y: event.clientY,
    panX: pan.value.x,
    panY: pan.value.y,
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
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
  try {
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
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

const insertAfterId = ref<string | null>(null)
const insertOpen = computed({
  get: () => insertAfterId.value !== null,
  set: (open: boolean) => {
    if (!open) insertAfterId.value = null
  },
})

function openInsert(afterId: string): void {
  if (!props.readonly) insertAfterId.value = afterId
}

function chooseInsert(type: AddableNodeType): void {
  const afterId = insertAfterId.value
  if (!afterId) return
  const node = makeNode(props.definition, type)
  if (insertAfter(props.definition, afterId, node)) {
    emit('change')
    emit('update:selectedId', node.id)
  }
  insertAfterId.value = null
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
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
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

    <a-modal v-model:open="insertOpen" title="插入节点" :footer="null">
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
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npm run typecheck`

Expected: PASS。若 `a-space` 在 `script setup` 中未导入也没关系 —— antd 是全局注册的（见 TECH-DESIGN §6.3）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/flow-designer/canvas/FlowCanvas.vue
git commit -m "feat(M7): 流程画布容器与拖拽交互"
```

---

## Task 5: 设计器接入画布视图

**Files:**
- Modify: `frontend/src/views/admin/flow/FlowDesignerView.vue`

- [ ] **Step 1: 替换本地节点操作与工厂**

修改 imports：

```ts
import FlowCanvas from '@/components/flow-designer/canvas/FlowCanvas.vue'
import {
  ADDABLE_NODES,
  findLocation,
  findNode,
  makeNode,
  moveWithinSiblings,
  removeNode,
  type AddableNodeType,
} from '@/components/flow-designer/definitionOps'
```

删除本文件的 `findNode`、`removeNode`、`moveNode`、`uniqueId`、`makeApproval`、`makeFill`、`makeCc`、`makeCondition`、`makeParallel`、`ADDABLE`。

替换 `addNode`：

```ts
function addNode(type: AddableNodeType, into?: StepNode[]): void {
  if (!definition.value) return
  const node = makeNode(definition.value, type)
  ;(into ?? definition.value.steps).push(node)
  selectedId.value = node.id
  scheduleSave()
}
```

替换 `deleteSelected` / `moveSelected`：

```ts
function deleteSelected(): void {
  const id = selectedId.value
  if (!id || !definition.value) return
  const node = findNode(definition.value, id)
  if (!node) return
  if (!window.confirm(`删除节点「${node.name}」？其中配置的审批人与字段权限会一并移除。`)) return
  if (removeNode(definition.value, id)) {
    selectedId.value = definition.value.steps[0]?.id ?? null
    scheduleSave()
  }
}

function moveSelected(delta: number): void {
  const id = selectedId.value
  if (!id || !definition.value) return
  const location = findLocation(definition.value, id)
  if (!location) return
  if (moveWithinSiblings(definition.value, id, location.index + delta)) scheduleSave()
}
```

`selectedNode` 继续使用导入的 `findNode`；`nodeNameById` 不变。

- [ ] **Step 2: 增加视图切换**

在 `const selectedId = ref...` 附近增加：

```ts
const viewMode = ref<'canvas' | 'list'>('canvas')
```

在 header 的标题 `Space` 中加入：

```html
<a-radio-group v-model:value="viewMode" size="small" button-style="solid">
  <a-radio-button value="canvas">画布</a-radio-button>
  <a-radio-button value="list">清单</a-radio-button>
</a-radio-group>
```

- [ ] **Step 3: 改 designer-body 布局**

把原来的 `<a-col :xs="24" :md="9" :lg="7">` 左侧卡片替换为按 `viewMode` 切换：

```html
<a-col :xs="24" :md="viewMode === 'canvas' ? 16 : 9" :lg="viewMode === 'canvas' ? 17 : 7">
  <Card v-if="viewMode === 'canvas'" :bordered="false" :loading="loading" class="panel canvas-panel">
    <FlowCanvas
      v-if="definition"
      v-model:selected-id="selectedId"
      :definition="definition"
      :readonly="readonly"
      @change="onNodeChange"
    />
    <a-empty v-else description="还没有流程定义" />
  </Card>

  <Card v-else :bordered="false" :loading="loading" class="panel">
    <!-- 这里保留原来的「左侧节点清单」卡片内容，不删任何现有逻辑 -->
  </Card>
</a-col>
```

把右侧属性面板的列改为：

```html
<a-col :xs="24" :md="viewMode === 'canvas' ? 8 : 15" :lg="viewMode === 'canvas' ? 7 : 17">
```

- [ ] **Step 4: 替换清单里的 ADDABLE 引用**

把模板里所有 `v-for="opt in ADDABLE"` 改为 `v-for="opt in ADDABLE_NODES"`，`:key="opt.key"` 改为 `:key="opt.type"`，`@click="addNode(opt.make)"` 改为 `@click="addNode(opt.type)"`。

过滤条件同步改为按 `opt.type`：

```html
v-for="opt in selectedNode.type === 'parallel'
  ? ADDABLE_NODES.filter((a) => a.type === 'approval' || a.type === 'fill')
  : ADDABLE_NODES.filter((a) => a.type !== 'parallel')"
:key="opt.type"
@click="addNode(opt.type, ...)"
```

- [ ] **Step 5: 增加画布面板样式**

在 `<style scoped>` 中增加：

```scss
.canvas-panel {
  min-height: 640px;

  :deep(.ant-card-body) {
    padding: 8px;
  }
}
```

- [ ] **Step 6: 类型检查与现有测试**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run src/__tests__/render.spec.ts
```

Expected: PASS。FlowDesignerView 默认进入画布，mock 的流程定义应能渲染；若报 `findNode` 未定义，说明还有旧调用点未替换。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/admin/flow/FlowDesignerView.vue
git commit -m "feat(M7): 设计器接入画布视图"
```

---

## Task 6: 画布组件测试与全量回归

**Files:**
- Create: `frontend/src/components/flow-designer/canvas/FlowCanvas.spec.ts`
- Modify: `frontend/src/__tests__/render.spec.ts`（仅在需要补断言时）
- Modify: `docs/PHASE2-DESIGN.md`、`docs/TECH-DESIGN.md`、`README.md`

- [ ] **Step 1: 写画布组件测试**

创建 `FlowCanvas.spec.ts`：

```ts
import Antd from 'ant-design-vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import FlowCanvas from '@/components/flow-designer/canvas/FlowCanvas.vue'
import { findNode } from '@/components/flow-designer/definitionOps'
import type { FlowDefinition, StepNode } from '@/types/flow'

function approval(id: string): StepNode {
  return {
    id, type: 'approval', name: id,
    assignee: { mode: 'SINGLE', sources: [] },
    reject_policy: 'reject_to_initiator',
    return_targets: null, timeout_hours: null,
    opinion_required: false, attachment_required: false,
    fields_permission: { base: 'readonly', partitions: {}, overrides: {}, conditional_overrides: [] },
  }
}

function definition(): FlowDefinition {
  return {
    model_version: 1,
    start: { id: 'start', type: 'start', name: '发起', fields_permission: null },
    steps: [approval('s1'), approval('s2')],
    end: { id: 'end', type: 'end', name: '结束' },
  }
}

function mountCanvas(def = definition()) {
  return mount(FlowCanvas, {
    props: { definition: def, selectedId: null, readonly: false },
    global: { plugins: [Antd] },
  })
}

describe('FlowCanvas', () => {
  it('渲染节点卡片与连线', () => {
    const wrapper = mountCanvas()
    expect(wrapper.findAll('[data-node-id]').length).toBe(4)
    expect(wrapper.findAll('path').length).toBeGreaterThanOrEqual(3)
    wrapper.unmount()
  })

  it('点击节点发出选中事件', async () => {
    const wrapper = mountCanvas()
    await wrapper.find('[data-node-id="s1"]').trigger('click')
    expect(wrapper.emitted('update:selectedId')?.[0]).toEqual(['s1'])
    wrapper.unmount()
  })

  it('删除节点会修改定义并发出 change', async () => {
    const def = definition()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mountCanvas(def)
    await wrapper.find('[data-node-id="s1"] [title="删除节点"]').trigger('click')
    expect(findNode(def, 's1')).toBeNull()
    expect(wrapper.emitted('change')).toBeTruthy()
    wrapper.unmount()
  })

  it('拖拽到另一个节点前面会重排', async () => {
    const def = definition()
    const wrapper = mountCanvas(def)
    const dataTransfer = {
      effectAllowed: '',
      setData: vi.fn(),
    } as unknown as DataTransfer

    await wrapper.find('[data-node-id="s2"]').trigger('dragstart', { dataTransfer })
    const target = wrapper.find('[data-node-id="s1"]')
    vi.spyOn(target.element as HTMLElement, 'getBoundingClientRect').mockReturnValue({
      top: 0, bottom: 100, height: 100, left: 0, right: 100, width: 100, x: 0, y: 0,
      toJSON: () => ({}),
    } as DOMRect)
    await target.trigger('dragover', { clientY: 10, dataTransfer })
    await target.trigger('drop', { clientY: 10, dataTransfer })

    expect(def.steps.map((s) => s.id)).toEqual(['s2', 's1'])
    expect(wrapper.emitted('change')).toBeTruthy()
    wrapper.unmount()
  })
})
```

- [ ] **Step 2: 运行画布测试**

Run: `cd frontend && npx vitest run src/components/flow-designer/canvas/FlowCanvas.spec.ts`

Expected: PASS。若 happy-dom 的拖拽事件不完整，保留前三个测试，把拖拽用例移到 `definitionOps.spec.ts` 的 `moveNodeTo` 覆盖（不要删掉纯函数测试）。

- [ ] **Step 3: 全量校验**

Run: `bash scripts/check.sh`

Expected: 五项全绿（pytest + ruff + vue-tsc + vitest + vite build）。若时间不够，先跑 `bash scripts/check.sh frontend`，收尾再跑全量。

- [ ] **Step 4: 同步文档**

- `docs/PHASE2-DESIGN.md`：把 M7 状态从“开工”改为“已完成”，补一行 M7 实际测试项。
- `docs/TECH-DESIGN.md` §7：M7 行标记完成，验收写“画布与清单共用定义；示例流程可编辑”。
- `docs/TECH-DESIGN.md` §8：补 M7 测试项（布局/操作/画布渲染）。
- `README.md` 的「后续里程碑」表补 M7 ✅。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/flow-designer/canvas/FlowCanvas.spec.ts docs/PHASE2-DESIGN.md docs/TECH-DESIGN.md README.md
git commit -m "test(M7): 画布组件测试与里程碑状态"
```

---

## 自检

- **Spec coverage**：M7 设计中的自动布局、节点增删、同级拖拽、条件/并行组操作、清单/画布切换、复用属性面板、无坐标持久化，均有对应任务。
- **Placeholder scan**：无 TBD/TODO；所有新增文件均给出完整代码或精确修改点。
- **Type consistency**：`CanvasNode` / `CanvasLane` / `CanvasGroup` / `DropTarget` / `NodeContainer` / `AddableNodeType` 在 layout、ops、组件与测试中使用同一套命名；`makeNode` 返回 `StepNode`，`insertAfter` 接受 `StepNode`。

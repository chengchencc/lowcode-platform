import { describe, expect, it } from 'vitest'

import {
  addBranch,
  addParallelMember,
  collectNodeIds,
  findLocation,
  findNode,
  insertAfter,
  insertIntoContainer,
  makeNode,
  moveNodeTo,
  moveWithinSiblings,
  removeNode,
} from '@/components/flow-designer/definitionOps'
import type { ApprovalNode, FillNode, FlowDefinition } from '@/types/flow'

function approval(id: string, name = id): ApprovalNode {
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

function fill(id: string, name = id): FillNode {
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

  it('拖入条件分支与并行组', () => {
    const def = definition()
    expect(moveNodeTo(def, 's1', {
      kind: 'container', container: { kind: 'branch', conditionId: 'c1', branchId: 'b1' },
    })).toBe(true)
    const condition = findNode(def, 'c1')
    if (condition?.type === 'condition') {
      expect(condition.branches[0].steps.map((s) => s.id)).toEqual(['s2', 's1'])
    } else {
      throw new Error('c1 应该是条件节点')
    }

    // 审批节点可以进入并行组
    expect(moveNodeTo(def, 's1', {
      kind: 'container', container: { kind: 'parallel', parallelId: 'p1' },
    })).toBe(true)
    expect(def.steps.map((s) => s.id)).toEqual(['c1', 'p1', 'cc1'])
    const parallel = findNode(def, 'p1')
    if (parallel?.type === 'parallel') {
      expect(parallel.members.map((m) => m.id)).toEqual(['m1', 'm2', 's1'])
    } else {
      throw new Error('p1 应该是并行组')
    }
  })

  it('容器不能进入自己的子树', () => {
    const def = definition()
    expect(moveNodeTo(def, 'c1', {
      kind: 'container', container: { kind: 'branch', conditionId: 'c1', branchId: 'b1' },
    })).toBe(false)
  })

  it('可以直接向根、条件分支与并行组插入节点', () => {
    const def = definition()
    expect(insertIntoContainer(def, { kind: 'root' }, approval('s0'))).toBe(true)
    expect(def.steps.at(-1)?.id).toBe('s0')

    expect(insertIntoContainer(
      def,
      { kind: 'branch', conditionId: 'c1', branchId: 'b1' },
      approval('s5'),
    )).toBe(true)
    const condition = findNode(def, 'c1')
    if (condition?.type !== 'condition') throw new Error('c1 应该是条件节点')
    expect(condition.branches[0].steps.map((s) => s.id)).toEqual(['s2', 's5'])

    expect(insertIntoContainer(
      def,
      { kind: 'parallel', parallelId: 'p1' },
      approval('m5'),
    )).toBe(true)
    const parallel = findNode(def, 'p1')
    if (parallel?.type !== 'parallel') throw new Error('p1 应该是并行组')
    expect(parallel.members.map((m) => m.id)).toEqual(['m1', 'm2', 'm5'])
  })

  it('直接插入时遵守容器约束与 id 唯一性', () => {
    const def = definition()
    expect(insertIntoContainer(def, { kind: 'root' }, approval('s1'))).toBe(false)
    expect(insertIntoContainer(
      def,
      { kind: 'parallel', parallelId: 'p1' },
      makeNode(def, 'condition'),
    )).toBe(false)
    expect(insertIntoContainer(
      def,
      { kind: 'branch', conditionId: 'c1', branchId: 'b1' },
      makeNode(def, 'parallel'),
    )).toBe(false)
    expect(insertIntoContainer(
      def,
      { kind: 'branch', conditionId: 'missing', branchId: 'b1' },
      approval('x'),
    )).toBe(false)
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

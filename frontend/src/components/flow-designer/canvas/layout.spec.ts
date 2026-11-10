import { describe, expect, it } from 'vitest'

import { buildCanvasLayout } from '@/components/flow-designer/canvas/layout'
import type { ApprovalNode, FlowDefinition, StepNode } from '@/types/flow'

function approval(id: string): ApprovalNode {
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

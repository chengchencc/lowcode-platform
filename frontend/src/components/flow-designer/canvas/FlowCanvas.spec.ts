import Antd from 'ant-design-vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import FlowCanvas from '@/components/flow-designer/canvas/FlowCanvas.vue'
import { findNode } from '@/components/flow-designer/definitionOps'
import type { ApprovalNode, FlowDefinition } from '@/types/flow'

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
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
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

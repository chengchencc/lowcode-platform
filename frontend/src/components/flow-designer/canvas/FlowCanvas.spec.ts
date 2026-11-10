import Antd from 'ant-design-vue'
import { flushPromises, mount } from '@vue/test-utils'
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

  it('pointerdown 落在图标 SVG 上时不应让画布捕获指针', async () => {
    const wrapper = mountCanvas()
    const viewport = wrapper.find('.canvas-viewport').element as HTMLElement
    const capture = vi.fn()
    viewport.setPointerCapture = capture

    // 图标内部是 <path>（SVGElement，不是 HTMLElement）。
    // 曾经用 `instanceof HTMLElement` 判断，漏掉 SVG，viewport 捕获指针后
    // pointerup/click 都落到 viewport，节点按钮永远不响应。
    const path = wrapper.find('[data-node-id="s1"] [title="在后面插入节点"] path').element
    path.dispatchEvent(new MouseEvent('pointerdown', {
      bubbles: true, button: 0, clientX: 100, clientY: 100,
    }))

    expect(capture, '按钮区域不应触发画布平移/指针捕获').not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('点击节点上的 + 会打开插入弹窗并新增节点', async () => {
    const def = definition()
    const wrapper = mountCanvas(def)
    const before = def.steps.length

    await wrapper.find('[data-node-id="s1"] [title="在后面插入节点"]').trigger('click')
    await flushPromises()

    const bodyText = document.body.textContent?.replace(/\s+/g, '') ?? ''
    expect(bodyText).toContain('插入节点')

    const option = Array.from(document.body.querySelectorAll('button'))
      .find((button) => button.textContent?.replace(/\s+/g, '') === '审批节点')
    expect(option, '弹窗里应有「审批节点」选项').toBeTruthy()
    option!.click()
    await flushPromises()

    expect(def.steps.length).toBe(before + 1)
    expect(wrapper.emitted('change')).toBeTruthy()
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

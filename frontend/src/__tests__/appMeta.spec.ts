import { beforeEach, describe, expect, it } from 'vitest'

import { appName, brandInitial, pageTitle } from '@/utils/appMeta'

describe('appMeta', () => {
  beforeEach(() => {
    appName.value = 'FlowForm'
  })

  it('brandInitial 中文取前两字，拉丁名称取两个大写字母', () => {
    expect(brandInitial('FlowForm')).toBe('FF')
    expect(brandInitial('OA 审批平台')).toBe('OA')
    expect(brandInitial('流程平台')).toBe('流程')
    expect(brandInitial('   ')).toBe('FF')
  })

  it('pageTitle 跟随配置的系统名称', () => {
    appName.value = '内部审批平台'
    expect(pageTitle('工作台')).toBe('工作台 · 内部审批平台')
    expect(pageTitle()).toBe('内部审批平台')
  })
})

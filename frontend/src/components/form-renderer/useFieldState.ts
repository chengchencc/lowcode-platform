/**
 * 表单字段的三态解析（PRD §3.4 机制 A/B 的前端侧）。
 *
 * 三态 = hidden / readonly / editable。渲染器**只读这份状态**，
 * 不自己判断权限 —— 保证「编辑态 / 只读态 / 权限态」是同一套渲染树（决策 D3）。
 *
 * **M2 阶段**：权限来自 schema 自身的 `visible_at_start` 与渲染模式。
 * **M3 起**：这些状态改由服务端按「节点 × 字段」的权限矩阵下发
 * （`GET /instances/{id}/render` 返回的 `permissions`），本模块会接收它而非自行推导。
 * 因此这里的函数签名刻意与将来的服务端结果保持同构。
 */

import type {
  FieldDef,
  FieldState,
  FormSchema,
  RenderMode,
  SectionDef,
  SectionStage,
} from '@/types/form'
import { DISPLAY_FIELD_TYPES } from '@/types/form'

// 类型定义放在 types/form.ts（与其余 schema 类型同处），这里只做转出方便使用
export type { FieldState, RenderMode }

/** 计算字段（公式）永远只读 —— 值由服务端与前端算出来，不接受用户输入。 */
function isComputed(field: FieldDef): boolean {
  return field.type === 'formula'
}

function resolveOne(field: FieldDef, mode: RenderMode): FieldState {
  if (DISPLAY_FIELD_TYPES.includes(field.type)) {
    // 展示控件不是数据字段：永远只读、不必填；可见性由分区/节点权限决定
    return { visible: true, editable: false, required: false }
  }

  const required = mode === 'edit' && !isComputed(field) && Boolean(field.required)

  if (mode === 'preview' || mode === 'readonly') {
    // 预览与只读态：全部可见、全部不可编辑
    return { visible: true, editable: false, required: false }
  }

  // edit 态：发起阶段的默认语义（PRD §3.2.2）
  //   visible_at_start = true  → 可见可编辑
  //   visible_at_start = false → 该字段是「某节点专属的补充字段」，发起阶段隐藏
  return {
    visible: field.visible_at_start !== false,
    editable: !isComputed(field),
    required,
  }
}

/** 整份 schema 的字段状态表，键为字段 key（子表列为 `subtable[].column`）。 */
export function resolveFieldStates(
  schema: FormSchema,
  mode: RenderMode,
): Record<string, FieldState> {
  const states: Record<string, FieldState> = {}
  for (const section of schema.sections) {
    for (const field of section.fields) {
      states[field.key] = resolveOne(field, mode)
      // 子表列跟随子表本体的可见性，行内不做独立的三态（M3 的权限矩阵也不细分到列）
      for (const col of field.columns ?? []) {
        states[`${field.key}[].${col.key}`] = resolveOne(col, mode)
      }
    }
  }
  return states
}

/** 分区内所有字段都隐藏时，整个分区不渲染（PRD §3.4 机制 B）。 */
export function sectionHasVisibleField(
  section: SectionDef,
  states: Record<string, FieldState>,
): boolean {
  return section.fields.some((f) => states[f.key]?.visible)
}

/** 分区阶段 → 视觉标签色，让设计器与填写页对「揭晓中」的补充区有直观感知。 */
export const STAGE_COLORS: Record<SectionStage, string> = {
  apply: 'blue',
  approve: 'gold',
  supplement: 'purple',
  archive: 'default',
}

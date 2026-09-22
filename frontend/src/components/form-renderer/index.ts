/**
 * 通用表单渲染器的对外入口。
 *
 * 外部只应从这里导入 —— 内部组件的拆分方式（SectionBlock / FieldControl /
 * controls/*）是实现细节，后续里程碑可能调整。
 */

export { default as FormRenderer } from './FormRenderer.vue'
export { default as SectionBlock } from './SectionBlock.vue'
export { default as FieldControl } from './FieldControl.vue'
export {
  resolveFieldStates,
  sectionHasVisibleField,
  STAGE_COLORS,
  type FieldState,
  type RenderMode,
} from './useFieldState'

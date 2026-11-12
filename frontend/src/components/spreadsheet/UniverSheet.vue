<script setup lang="ts">
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import zhCN from '@univerjs/preset-sheets-core/locales/zh-CN'
import '@univerjs/preset-sheets-core/lib/index.css'
import { createUniver, LocaleType, mergeLocales, type Univer } from '@univerjs/presets'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  snapshot: Record<string, unknown> | null
  readonly?: boolean
}>()
const emit = defineEmits<{ change: []; ready: [] }>()

const container = ref<HTMLElement | null>(null)
let univer: Univer | null = null
let univerAPI: ReturnType<typeof createUniver>['univerAPI'] | null = null
let workbookId: string | null = null
let commandSub: { dispose(): void } | null = null
let suppressChange = false

function install(snapshot: Record<string, unknown> | null): void {
  if (!univerAPI) return
  if (workbookId) {
    univerAPI.disposeUnit(workbookId)
    workbookId = null
  }
  const workbook = univerAPI.createWorkbook(snapshot ?? {})
  workbookId = workbook.getId()
  workbook.setEditable(!props.readonly)
}

onMounted(async () => {
  // 等 Ant Card 的布局完成：容器没有实际高度时 Univer 会把画布初始化成 0 高，
  // 表现就是工具栏/sheet 标签正常、网格区域全白。
  await nextTick()
  if (!container.value) return
  const created = createUniver({
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: mergeLocales(zhCN),
    },
    presets: [
      UniverSheetsCorePreset({
        container: container.value,
      }),
    ],
  })
  univer = created.univer
  univerAPI = created.univerAPI
  install(props.snapshot)
  commandSub = univerAPI.addEvent(univerAPI.Event.CommandExecuted, (event) => {
    // 只有 MUTATION 会改动快照；选择单元格、滚动等 OPERATION 不应触发保存
    if (!suppressChange && event.type === univerAPI!.Enum.CommandType.MUTATION) {
      emit('change')
    }
  })
  emit('ready')
})

watch(
  () => props.snapshot,
  (snapshot) => {
    if (!univerAPI) return
    suppressChange = true
    install(snapshot)
    suppressChange = false
  },
)

watch(
  () => props.readonly,
  (readonly) => {
    univerAPI?.getActiveWorkbook()?.setEditable(!readonly)
  },
)

onBeforeUnmount(() => {
  commandSub?.dispose()
  commandSub = null
  univer?.dispose()
  univer = null
  univerAPI = null
  workbookId = null
})

function getSnapshot(): Record<string, unknown> | null {
  const workbook = univerAPI?.getActiveWorkbook()
  return workbook ? (workbook.save() as unknown as Record<string, unknown>) : null
}

defineExpose({ getSnapshot })
</script>

<template>
  <div ref="container" class="univer-container" />
</template>

<style scoped>
.univer-container {
  width: 100%;
  /* 必须给出可解析的高度（不能只写 100%）：Univer 的 Canvas 按容器实际高度布局 */
  height: calc(100vh - 220px);
  min-height: 520px;
}
</style>

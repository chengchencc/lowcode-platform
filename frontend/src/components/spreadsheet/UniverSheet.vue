<script setup lang="ts">
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import zhCN from '@univerjs/preset-sheets-core/locales/zh-CN'
import '@univerjs/preset-sheets-core/lib/index.css'
import { createUniver, LocaleType, mergeLocales, type Univer } from '@univerjs/presets'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

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

onMounted(() => {
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
  commandSub = univerAPI.addEvent(univerAPI.Event.CommandExecuted, () => {
    if (!suppressChange) emit('change')
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
  height: 100%;
  min-height: 480px;
}
</style>

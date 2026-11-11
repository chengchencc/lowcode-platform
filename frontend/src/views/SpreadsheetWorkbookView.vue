<script setup lang="ts">
import { ArrowLeftOutlined, DownloadOutlined } from '@ant-design/icons-vue'
import { Alert, Button, Card, Space, Tag } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { spreadsheetApi } from '@/api/modules/spreadsheet'
import UniverSheet from '@/components/spreadsheet/UniverSheet.vue'
import type { SpreadsheetDetail } from '@/types/spreadsheet'
import { formatDateTime, formatRelative } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'
import { exportSnapshotToXlsx } from '@/utils/spreadsheetExport'

const route = useRoute()
const router = useRouter()
const workbookId = computed(() => Number(route.params.id))

const detail = ref<SpreadsheetDetail | null>(null)
const version = ref(0)
const remoteSnapshot = ref<Record<string, unknown> | null>(null)
const sheetRef = ref<InstanceType<typeof UniverSheet> | null>(null)

const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const conflict = ref(false)
const lastSavedAt = ref<string | null>(null)
const lastSavedBy = ref<string | null>(null)

const SAVE_DELAY = 1500
const POLL_INTERVAL = 5000

let saveTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

const saveStateText = computed(() => {
  if (conflict.value) return '有冲突'
  if (saving.value) return '保存中…'
  if (dirty.value) return '有未保存的改动'
  if (lastSavedAt.value) return `已保存 · ${formatRelative(lastSavedAt.value)}`
  return '已同步'
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await spreadsheetApi.get(workbookId.value)
    detail.value = data
    version.value = data.version
    remoteSnapshot.value = data.snapshot
    lastSavedAt.value = data.updated_at
    lastSavedBy.value = data.updated_by_name
  } finally {
    loading.value = false
  }
}

function scheduleSave(): void {
  if (!detail.value?.can_edit || conflict.value) return
  dirty.value = true
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void save(), SAVE_DELAY)
}

async function save(): Promise<void> {
  if (!detail.value?.can_edit || saving.value || conflict.value) return
  const snapshot = sheetRef.value?.getSnapshot()
  if (!snapshot) return
  saving.value = true
  try {
    const result = await spreadsheetApi.save(workbookId.value, snapshot, version.value)
    version.value = result.version
    lastSavedAt.value = result.updated_at
    lastSavedBy.value = result.updated_by_name
    dirty.value = false
  } catch (error) {
    if (error instanceof ApiError && error.code === 'SPREADSHEET_VERSION_CONFLICT') {
      conflict.value = true
      const name = (error.extra?.updated_by_name as string | null) ?? '他人'
      feedback.error(`工作簿已被${name}修改，请选择加载最新或覆盖保存`)
    }
  } finally {
    saving.value = false
  }
}

async function loadLatest(): Promise<void> {
  if (saveTimer) clearTimeout(saveTimer)
  const state = await spreadsheetApi.state(workbookId.value, 0)
  if (state.snapshot) remoteSnapshot.value = state.snapshot
  version.value = state.version
  lastSavedAt.value = state.updated_at
  lastSavedBy.value = state.updated_by_name
  conflict.value = false
  dirty.value = false
  feedback.success('已加载最新版本')
}

async function overwrite(): Promise<void> {
  if (!detail.value?.can_edit) return
  const snapshot = sheetRef.value?.getSnapshot()
  if (!snapshot) return
  const state = await spreadsheetApi.state(workbookId.value, 0)
  saving.value = true
  try {
    const result = await spreadsheetApi.save(workbookId.value, snapshot, state.version)
    version.value = result.version
    lastSavedAt.value = result.updated_at
    lastSavedBy.value = result.updated_by_name
    conflict.value = false
    dirty.value = false
    feedback.success('已覆盖保存')
  } catch (error) {
    if (error instanceof ApiError && error.code === 'SPREADSHEET_VERSION_CONFLICT') {
      feedback.error('刚又有人保存了，请重新加载后再试')
    }
  } finally {
    saving.value = false
  }
}

async function poll(): Promise<void> {
  if (!detail.value || saving.value) return
  try {
    const state = await spreadsheetApi.state(workbookId.value, version.value)
    if (!state.changed) return
    if (dirty.value || saving.value) {
      conflict.value = true
      return
    }
    if (state.snapshot) {
      remoteSnapshot.value = state.snapshot
      version.value = state.version
      lastSavedAt.value = state.updated_at
      lastSavedBy.value = state.updated_by_name
    }
  } catch {
    // 轮询失败静默
  }
}

function onReady(): void {
  // 新建的空工作簿：Univer 已生成默认 sheet，立即落一份快照
  if (!detail.value?.snapshot) scheduleSave()
}

function doExport(): void {
  const snapshot = sheetRef.value?.getSnapshot()
  if (!snapshot) return
  try {
    exportSnapshotToXlsx(snapshot, detail.value?.name ?? '共享表格')
    feedback.success('已导出 Excel')
  } catch (error) {
    feedback.error(error instanceof Error ? error.message : '导出失败')
  }
}

onMounted(async () => {
  await load()
  pollTimer = setInterval(() => void poll(), POLL_INTERVAL)
})

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
  if (pollTimer) clearInterval(pollTimer)
  if (dirty.value) void save()
})
</script>

<template>
  <div class="page-container sheet-page">
    <Card v-if="detail" :bordered="false" class="sheet-card" :loading="loading">
      <template #title>
        <Space>
          <Button type="text" @click="router.push({ name: 'spreadsheets' })">
            <template #icon><ArrowLeftOutlined /></template>
          </Button>
          <span>{{ detail.name }}</span>
          <Tag v-if="!detail.can_edit" color="default">只读</Tag>
          <Tag color="blue">v{{ version }}</Tag>
        </Space>
      </template>
      <template #extra>
        <Space :size="8" wrap>
          <span class="text-muted save-state">
            {{ saveStateText }}
            <template v-if="lastSavedBy"> · {{ lastSavedBy }}</template>
          </span>
          <Button @click="doExport">
            <template #icon><DownloadOutlined /></template>
            导出 Excel
          </Button>
        </Space>
      </template>

      <Alert
        v-if="conflict"
        type="warning"
        show-icon
        class="conflict"
        message="工作簿已被他人修改"
        description="你可以加载最新版本（放弃本地改动），或用当前内容覆盖保存。"
      >
        <template #action>
          <Space>
            <Button size="small" @click="loadLatest">加载最新</Button>
            <Button size="small" danger @click="overwrite">覆盖保存</Button>
          </Space>
        </template>
      </Alert>

      <UniverSheet
        ref="sheetRef"
        :snapshot="remoteSnapshot"
        :readonly="!detail.can_edit"
        @change="scheduleSave"
        @ready="onReady"
      />

      <div class="text-muted footer-hint">
        编辑会自动保存；其他人每 5 秒同步一次。最后更新：{{ formatDateTime(lastSavedAt) }}
      </div>
    </Card>
  </div>
</template>

<style scoped lang="scss">
.sheet-page {
  max-width: 1600px;
  margin: 0 auto;
}

.sheet-card {
  border-radius: 8px;
}

.save-state {
  font-size: 12px;
}

.conflict {
  margin-bottom: 10px;
}

.footer-hint {
  margin-top: 8px;
  font-size: 12px;
}
</style>

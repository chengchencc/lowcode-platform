<script setup lang="ts">
import { ArrowLeftOutlined, DownloadOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons-vue'
import {
  Alert,
  Button,
  Card,
  Empty,
  Modal,
  Space,
  Table,
  Tag,
  Upload,
} from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VxeColumn, VxeTable } from 'vxe-table'
import 'vxe-table/lib/style.css'

import { ApiError } from '@/api/http'
import { workStatApi } from '@/api/modules/workStat'
import type {
  WorkStatColumn,
  WorkStatImportPreview,
  WorkStatRow,
  WorkStatRowLog,
  WorkStatSheet,
} from '@/types/workStat'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

interface GridRow {
  _key: string
  id: number | null
  row_no: number
  version: number
  updated_at: string | null
  // 列 key 由后端限制为安全标识，外层字段不会与列冲突
  [key: string]: any
}

const route = useRoute()
const router = useRouter()
const sheetId = computed(() => Number(route.params.id))

const sheet = ref<WorkStatSheet | null>(null)
const gridRows = ref<GridRow[]>([])
const loading = ref(false)
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const editingKey = ref<string | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let newRowSeq = 0

function toGrid(row: WorkStatRow): GridRow {
  return {
    _key: String(row.id),
    id: row.id,
    row_no: row.row_no,
    version: row.version,
    updated_at: row.updated_at,
    ...row.cells,
  }
}

function cellsOf(row: GridRow): Record<string, unknown> {
  const cells: Record<string, unknown> = {}
  for (const column of sheet.value?.columns ?? []) {
    const value = row[column.key]
    cells[column.key] = value === undefined || value === null ? '' : value
  }
  return cells
}

function displayValue(row: GridRow, column: WorkStatColumn): string {
  const value = row[column.key]
  if (value === undefined || value === null || value === '') return ''
  return String(value)
}

async function loadSheet(): Promise<void> {
  sheet.value = await workStatApi.getSheet(sheetId.value)
}

async function loadRows(): Promise<void> {
  const rows = await workStatApi.rows(sheetId.value)
  gridRows.value = rows.map(toGrid)
}

async function load(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([loadSheet(), loadRows()])
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function onEditActivated({ row }: { row: GridRow }): void {
  editingKey.value = row._key
}

async function onEditClosed({ row }: { row: GridRow }): Promise<void> {
  editingKey.value = null
  await saveRow(row)
}

async function saveRow(row: GridRow): Promise<void> {
  if (!sheet.value?.can_edit) return
  saveState.value = 'saving'
  try {
    const saved = row.id
      ? await workStatApi.updateRow(sheetId.value, row.id, cellsOf(row), row.version)
      : await workStatApi.createRow(sheetId.value, cellsOf(row))
    Object.assign(row, toGrid(saved))
    saveState.value = 'saved'
  } catch (error) {
    saveState.value = 'error'
    if (error instanceof ApiError && error.code === 'WORK_STAT_ROW_CONFLICT') {
      feedback.error('该行已被他人修改，正在刷新')
      await loadRows()
    }
  }
}

function addRow(): void {
  newRowSeq += 1
  gridRows.value.push({
    _key: `new-${newRowSeq}`,
    id: null,
    row_no: gridRows.value.length + 1,
    version: 0,
    updated_at: null,
  })
}

async function removeRow(row: GridRow): Promise<void> {
  if (row.id) {
    await workStatApi.deleteRow(sheetId.value, row.id)
  }
  gridRows.value = gridRows.value.filter((item) => item._key !== row._key)
  feedback.success('已删除')
}

// --------------------------------------------------------------------------- 行历史

const logsOpen = ref(false)
const logsLoading = ref(false)
const logs = ref<WorkStatRowLog[]>([])
const logsRowLabel = ref('')

async function showLogs(row: GridRow): Promise<void> {
  if (!row.id) return
  logsRowLabel.value = `第 ${row.row_no} 行`
  logsOpen.value = true
  logsLoading.value = true
  try {
    logs.value = await workStatApi.rowLogs(sheetId.value, row.id)
  } finally {
    logsLoading.value = false
  }
}

function changeSummary(log: WorkStatRowLog): string {
  if (log.action === 'CREATE' || log.action === 'IMPORT') return '新增行'
  if (log.action === 'DELETE') return '删除行'
  const before = log.before ?? {}
  const after = log.after ?? {}
  const changed = Object.keys(after).filter(
    (key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]),
  )
  if (!changed.length) return '无字段变化'
  return changed
    .map((key) => `${key}: ${before[key] ?? '—'} → ${after[key] ?? '—'}`)
    .join('；')
}

// --------------------------------------------------------------------------- Excel

const pendingFile = ref<File | null>(null)
const importOpen = ref(false)
const importPreview = ref<WorkStatImportPreview | null>(null)
const importing = ref(false)

async function onImportFile(file: File): Promise<boolean> {
  pendingFile.value = file
  try {
    importPreview.value = await workStatApi.importPreview(sheetId.value, file)
    importOpen.value = true
  } catch {
    pendingFile.value = null
  }
  return false
}

async function confirmImport(): Promise<void> {
  if (!pendingFile.value) return
  importing.value = true
  try {
    const result = await workStatApi.importFile(sheetId.value, pendingFile.value)
    feedback.success(`已导入 ${result.imported} 行`)
    importOpen.value = false
    pendingFile.value = null
    await loadRows()
  } finally {
    importing.value = false
  }
}

const previewColumns = computed(() =>
  (sheet.value?.columns ?? []).map((column) => ({
    title: column.label,
    dataIndex: column.key,
    key: column.key,
  })),
)

const previewRows = computed(() =>
  (importPreview.value?.preview_rows ?? []).map((row, index) => ({
    ...row,
    _key: String(index),
  })),
)

async function exportFile(): Promise<void> {
  const response = await workStatApi.exportFile(sheetId.value)
  const blob = new Blob([response.data], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${sheet.value?.name ?? 'work-stats'}.xlsx`
  link.click()
  URL.revokeObjectURL(url)
}

// --------------------------------------------------------------------------- 轮询

onMounted(async () => {
  await load()
  pollTimer = setInterval(async () => {
    if (editingKey.value) return
    try {
      await loadRows()
    } catch {
      // 轮询失败静默
    }
  }, 5_000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="page-container sheet-page">
    <Card v-if="sheet" :bordered="false" class="sheet-card">
      <template #title>
        <Space>
          <Button type="text" @click="router.push({ name: 'work-stats' })">
            <template #icon><ArrowLeftOutlined /></template>
          </Button>
          <span>{{ sheet.name }}</span>
          <Tag v-if="!sheet.can_edit" color="default">只读</Tag>
        </Space>
      </template>
      <template #extra>
        <Space :size="8" wrap>
          <span class="text-muted save-state">
            <template v-if="saveState === 'saving'">保存中…</template>
            <template v-else-if="saveState === 'saved'">已保存</template>
            <template v-else-if="saveState === 'error'">保存失败</template>
            <template v-else>{{ gridRows.length }} 行</template>
          </span>
          <Button v-if="sheet.can_edit" @click="addRow">
            <template #icon><PlusOutlined /></template>
            新增行
          </Button>
          <Upload
            v-if="sheet.can_edit"
            :show-upload-list="false"
            accept=".xlsx"
            :before-upload="onImportFile"
          >
            <Button>
              <template #icon><UploadOutlined /></template>
              导入 Excel
            </Button>
          </Upload>
          <Button @click="exportFile">
            <template #icon><DownloadOutlined /></template>
            导出 Excel
          </Button>
        </Space>
      </template>

      <div v-if="sheet.description" class="text-muted sheet-desc">{{ sheet.description }}</div>

      <VxeTable
        v-if="gridRows.length"
        :data="gridRows"
        :loading="loading"
        :row-config="{ keyField: '_key' }"
        :column-config="{ resizable: true }"
        :edit-config="sheet.can_edit ? { trigger: 'click', mode: 'cell', showStatus: true } : undefined"
        :clip-config="{ isCopy: true, isPaste: true }"
        border
        height="600"
        @edit-activated="onEditActivated"
        @edit-closed="onEditClosed"
      >
        <VxeColumn
          v-for="column in sheet.columns"
          :key="column.key"
          :field="column.key"
          :title="column.label"
          :width="column.width"
          :edit-render="sheet.can_edit ? {} : undefined"
        >
          <template #default="{ row }">
            {{ displayValue(row, column) }}
          </template>
          <template #edit="{ row }">
            <select
              v-if="column.type === 'select'"
              v-model="row[column.key]"
              class="cell-input"
            >
              <option value="" />
              <option v-for="option in column.options" :key="option" :value="option">
                {{ option }}
              </option>
            </select>
            <input
              v-else-if="column.type === 'number'"
              v-model="row[column.key]"
              class="cell-input"
              type="number"
            />
            <input
              v-else-if="column.type === 'date'"
              v-model="row[column.key]"
              class="cell-input"
              type="date"
            />
            <input v-else v-model="row[column.key]" class="cell-input" />
          </template>
        </VxeColumn>

        <VxeColumn v-if="sheet.can_edit" title="操作" width="110" fixed="right">
          <template #default="{ row }">
            <a @click="showLogs(row)">历史</a>
            <a-divider type="vertical" />
            <a-popconfirm title="删除该行？" @confirm="removeRow(row)">
              <a class="danger-link">删除</a>
            </a-popconfirm>
          </template>
        </VxeColumn>
      </VxeTable>
      <Empty v-else description="还没有数据，点击「新增行」开始填写" />

      <div v-if="sheet.can_edit" class="grid-hint text-muted">
        提示：可以直接从 Excel 复制多行，粘贴到表格里；修改会自动保存。
      </div>
    </Card>

    <Modal
      v-model:open="logsOpen"
      :title="`${logsRowLabel} 修改历史`"
      :footer="null"
      width="720px"
    >
      <a-spin :spinning="logsLoading">
        <div v-if="logs.length" class="log-list">
          <div v-for="log in logs" :key="log.id" class="log-row">
            <div class="log-head">
              <Tag>{{ log.action }}</Tag>
              <span>{{ log.actor_name ?? `#${log.actor_id}` }}</span>
              <span class="text-muted">{{ formatDateTime(log.created_at) }}</span>
            </div>
            <div class="log-detail text-muted">{{ changeSummary(log) }}</div>
          </div>
        </div>
        <Empty v-else description="暂无修改记录" />
      </a-spin>
    </Modal>

    <Modal
      v-model:open="importOpen"
      title="导入预览"
      :confirm-loading="importing"
      ok-text="确认导入"
      cancel-text="取消"
      width="800px"
      @ok="confirmImport"
    >
      <template v-if="importPreview">
        <Alert
          v-if="importPreview.warnings.length"
          type="warning"
          show-icon
          :message="importPreview.warnings.join('；')"
          class="mb"
        />
        <div class="import-summary text-muted">
          共识别 {{ importPreview.total_rows }} 行，下面展示前 {{ importPreview.preview_rows.length }} 行
        </div>
        <Table
          :columns="previewColumns"
          :data-source="previewRows"
          :pagination="false"
          size="small"
          bordered
          row-key="_key"
        />
      </template>
    </Modal>
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

.sheet-desc {
  margin-bottom: 12px;
  font-size: 12px;
}

.save-state {
  font-size: 12px;
}

.cell-input {
  width: 100%;
  height: 100%;
  padding: 2px 6px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
}

.danger-link {
  color: #ff4d4f;
}

.grid-hint {
  margin-top: 8px;
  font-size: 12px;
}

.mb {
  margin-bottom: 12px;
}

.import-summary {
  margin-bottom: 8px;
  font-size: 12px;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.log-row {
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}

.log-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.log-detail {
  margin-top: 4px;
  font-size: 12px;
  word-break: break-word;
}
</style>

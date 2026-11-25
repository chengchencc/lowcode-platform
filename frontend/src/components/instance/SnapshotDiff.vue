<script setup lang="ts">
/**
 * 快照对照（PRD F4.6 / §9 场景二「改单重提」）。
 *
 * 查看某个历史时点时，顺手给出「相对哪个时点，哪些字段变了」——
 * 驳回重提的争议基本都出在这里：改了什么、什么时候改的。
 *
 * 基准默认选**该时点的上一条快照**（驳回后重提场景下，就是上一轮提交），
 * 也可以自己挑任意一条来比。
 */
import { Table } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import { instanceApi } from '@/api/modules/instance'
import { useOrgStore } from '@/stores/org'
import type { FormSchema } from '@/types/form'
import type { ActionEntry } from '@/types/instance'
import { buildFieldIndex, fieldLabelIndex, formatReadableValue } from '@/utils/fieldValueDisplay'

const props = defineProps<{
  instanceId: number
  /** 当前正在查看的快照 */
  snapshotId: number
  actions: ActionEntry[]
  schema: FormSchema
  attachments?: Array<{ id: number; file_name: string }>
}>()

const ATable = Table
const org = useOrgStore()
const fields = computed(() => buildFieldIndex(props.schema))
const attachmentNames = computed(
  () => new Map((props.attachments ?? []).map((att) => [att.id, att.file_name])),
)

export interface SnapshotOption {
  id: number
  seq: number | null
  label: string
}

/** 有快照的动作 —— 一次提交/处理一个快照，按时间顺序 */
const options = computed<SnapshotOption[]>(() =>
  props.actions
    .filter((a) => a.snapshot_id != null)
    .map((a) => ({
      id: a.snapshot_id as number,
      seq: a.snapshot_seq,
      label: `#${a.snapshot_seq ?? '?'} ${a.action_label}（${a.actor_name}）`,
    })),
)

const currentIndex = computed(() => options.value.findIndex((o) => o.id === props.snapshotId))

/** 默认基准：上一条快照；没有上一条就取下一条 */
const defaultBaseline = computed<number | null>(() => {
  const index = currentIndex.value
  if (index > 0) return options.value[index - 1].id
  if (index === 0 && options.value.length > 1) return options.value[1].id
  return null
})

const baselineId = ref<number | null>(null)

watch(
  () => [props.snapshotId, props.instanceId],
  () => {
    baselineId.value = defaultBaseline.value
  },
  { immediate: true },
)

const rows = ref<Array<{ key: string; old: unknown; new: unknown }>>([])
const loading = ref(false)

/** 字段引用 → 中文标签（含子表列），差异表里要给人看的是标签 */
const labels = computed<Record<string, string>>(() => fieldLabelIndex(props.schema))

async function load(): Promise<void> {
  const baseline = baselineId.value
  if (baseline == null || baseline === props.snapshotId) {
    rows.value = []
    return
  }
  loading.value = true
  try {
    rows.value = await instanceApi.snapshotDiff(props.instanceId, baseline, props.snapshotId)
  } finally {
    loading.value = false
  }
}

watch([baselineId, () => props.snapshotId], () => void load(), { immediate: true })

function display(value: unknown, key: string): string {
  return formatReadableValue(value, fields.value.get(key), {
    userName: (id) => org.userName(id),
    deptName: (id) => org.deptName(id),
    attachmentName: (id) => attachmentNames.value.get(id),
  })
}

const columns = [
  { title: '字段', key: 'label', width: 220 },
  { title: '基准时点', key: 'old' },
  { title: '当前查看', key: 'new' },
]
</script>

<template>
  <a-card title="变更对照" :bordered="false" class="block">
    <template #extra>
      <a-space>
        <span class="text-muted hint">对比基准</span>
        <a-select
          v-model:value="baselineId"
          :options="options.filter((o) => o.id !== snapshotId).map((o) => ({ value: o.id, label: o.label }))"
          style="min-width: 220px"
          placeholder="没有可比对的时点"
        />
      </a-space>
    </template>

    <ATable
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      row-key="key"
      size="small"
      :pagination="false"
      :locale="{ emptyText: '这两个时点没有字段差异' }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'label'">
          {{ labels[record.key] ?? record.key }}
        </template>
        <template v-else-if="column.key === 'old'">
          <span class="text-muted">{{ display(record.old, record.key) }}</span>
        </template>
        <template v-else>
          <span class="new-value">{{ display(record.new, record.key) }}</span>
        </template>
      </template>
    </ATable>
  </a-card>
</template>

<style scoped lang="scss">
.block {
  border-radius: 8px;
  margin-bottom: 12px;
}

.hint {
  font-size: 12px;
}

.new-value {
  font-weight: 500;
}
</style>

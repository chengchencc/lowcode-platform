<script setup lang="ts">
/**
 * ★ 实例详情页（PRD §5「全部价值的交汇点」）。
 *
 * 版面自上而下：
 *   标题栏  单号/状态/发起人 + **处理按钮**（同意/驳回/退回，仅当前处理人可见）
 *           + 实例级操作（撤回/撤销/终止）
 *   表单    按**服务端下发的权限**渲染的分区表单（hidden 不渲染 / readonly 只读 / editable 可改）
 *   进度    并行组并列、条件分支标出实际走向（参考信息，放表单之后）
 *   时间线  处理历史，可回放快照
 *
 * 数据一次取全（`GET /instances/{id}/render`），避免分多次请求拼装导致的撕裂状态。
 */
import { ArrowLeftOutlined, HistoryOutlined, RollbackOutlined } from '@ant-design/icons-vue'
import { Button, Card, Modal, Space, Tag } from 'ant-design-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { instanceApi } from '@/api/modules/instance'
import { FormRenderer } from '@/components/form-renderer'
import ActionPanel from '@/components/instance/ActionPanel.vue'
import ProgressBar from '@/components/instance/ProgressBar.vue'
import TimelineList from '@/components/instance/TimelineList.vue'
import type { FieldState } from '@/types/form'
import type { InstanceRender } from '@/types/instance'
import { INSTANCE_STATUS_META, MY_ROLE_LABELS } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const route = useRoute()
const router = useRouter()

const instanceId = computed(() => Number(route.params.id))
const assignmentId = computed(() => {
  const raw = route.query.assignment
  return raw ? Number(raw) : undefined
})

const data = ref<InstanceRender | null>(null)
const loading = ref(false)
const activeSnapshotId = ref<number | null>(null)

/** 处理时改动的字段。只提交这些，服务端还会再按权限过滤一遍。 */
const fieldPatch = ref<Record<string, unknown>>({})

/** 表单当前值 = 服务端值 + 我的本地改动 */
const formValues = computed<Record<string, unknown>>(() => ({
  ...(data.value?.values ?? {}),
  ...fieldPatch.value,
}))

/** 只有「可编辑」的字段允许改；其余保持服务端下发 */
const permissions = computed<Record<string, FieldState>>(() => {
  const raw = data.value?.permissions ?? {}
  const out: Record<string, FieldState> = {}
  for (const [key, perm] of Object.entries(raw)) {
    out[key] = { visible: perm.visible, editable: perm.editable, required: perm.required }
  }
  return out
})

const canEditForm = computed(() => data.value?.my_role === 'CURRENT_HANDLER')

/** 详情页的表单模式：可编辑时用 edit，其余一律 readonly */
const formMode = computed<'edit' | 'readonly'>(() =>
  canEditForm.value ? 'edit' : 'readonly',
)

async function load(): Promise<void> {
  loading.value = true
  try {
    data.value = await instanceApi.render(instanceId.value, {
      assignment_id: assignmentId.value,
      snapshot_id: activeSnapshotId.value ?? undefined,
    })
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      feedback.error('你没有权限查看该单据')
      await router.replace({ name: 'workbench', params: { type: 'mine' } })
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([instanceId, activeSnapshotId], () => void load())

function onFormChange(values: Record<string, unknown>): void {
  // 只记录与已保存值不同的字段，避免把整表单都提交上去
  const baseline = data.value?.values ?? {}
  const patch: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(values)) {
    if (JSON.stringify(baseline[key]) !== JSON.stringify(value)) patch[key] = value
  }
  fieldPatch.value = patch
}

function clearPatch(): void {
  fieldPatch.value = {}
}

// --------------------------------------------------------------------------- 实例级操作

const terminateOpen = ref(false)
const terminateReason = ref('')
const operating = ref(false)

const canWithdraw = computed(
  () => data.value?.my_role === 'INITIATOR' && data.value.instance.status === 'RUNNING',
)
const canAbandon = computed(
  () => data.value?.my_role === 'INITIATOR' && data.value.instance.status === 'REJECTED',
)
const canTerminate = computed(
  () =>
    data.value?.my_role === 'ADMIN' &&
    !['APPROVED', 'WITHDRAWN', 'TERMINATED'].includes(data.value?.instance.status ?? ''),
)

/** 处理按钮（同意/驳回/退回）出现在标题栏的条件 */
const showHeaderActions = computed(() => canEditForm.value && !activeSnapshotId.value)
/** 实例级操作（撤回/撤销/终止）是否有可见项 —— 用于决定要不要分隔线 */
const showInstanceOps = computed(
  () => canWithdraw.value || canAbandon.value || canTerminate.value || !!activeSnapshotId.value,
)

async function doWithdraw(): Promise<void> {
  const ok = await feedback.confirm({
    title: '撤回该申请？',
    content: '仅在还没有任何人处理过时可以撤回。撤回后流程终止，需要重新发起。',
    danger: true,
  })
  if (!ok) return
  operating.value = true
  try {
    await instanceApi.withdraw(instanceId.value, null)
    feedback.success('已撤回')
    await load()
  } finally {
    operating.value = false
  }
}

async function doAbandon(): Promise<void> {
  const ok = await feedback.confirm({
    title: '放弃这轮申请？',
    content: '实例将变为「已撤回」，不可再重新提交。',
    danger: true,
  })
  if (!ok) return
  operating.value = true
  try {
    await instanceApi.abandon(instanceId.value)
    feedback.success('已撤销')
    await load()
  } finally {
    operating.value = false
  }
}

async function doTerminate(): Promise<void> {
  if (!terminateReason.value.trim()) {
    feedback.error('请填写终止原因')
    return
  }
  operating.value = true
  try {
    await instanceApi.terminate(instanceId.value, terminateReason.value.trim())
    terminateOpen.value = false
    terminateReason.value = ''
    feedback.success('已终止')
    await load()
  } finally {
    operating.value = false
  }
}

function viewSnapshot(snapshotId: number): void {
  activeSnapshotId.value = activeSnapshotId.value === snapshotId ? null : snapshotId
}

const statusMeta = computed(() =>
  data.value ? INSTANCE_STATUS_META[data.value.instance.status] : null,
)
</script>

<template>
  <div class="page-container detail-page" :class="{ loading }">
    <a-spin :spinning="loading">
      <template v-if="data">
        <!-- ------------------------------------------------ 顶部信息 -->
        <Card :bordered="false" class="header-card" :body-style="{ padding: '14px 18px' }">
          <div class="header-row">
            <Space align="start">
              <Button type="text" @click="router.back()">
                <template #icon><ArrowLeftOutlined /></template>
              </Button>
              <div>
                <div class="title-line">
                  <span class="title">{{ data.instance.title }}</span>
                  <Tag v-if="statusMeta" :color="statusMeta.color">{{ statusMeta.text }}</Tag>
                  <Tag v-if="data.instance.round > 1" color="purple">第 {{ data.instance.round }} 轮</Tag>
                  <Tag v-if="data.instance.abnormal" color="red">有异常任务</Tag>
                  <Tag color="blue">{{ MY_ROLE_LABELS[data.my_role] ?? data.my_role }}</Tag>
                </div>
                <div class="meta-line text-muted">
                  <span class="text-mono">{{ data.instance.code }}</span>
                  <span>{{ data.instance.flow_template_name }}</span>
                  <span>
                    发起人：{{ data.instance.initiator_name }}
                    <template v-if="data.instance.initiator_dept_name">
                      （{{ data.instance.initiator_dept_name }}）
                    </template>
                  </span>
                  <span v-if="data.instance.started_at">
                    提交于 {{ formatDateTime(data.instance.started_at) }}
                  </span>
                  <span v-if="data.instance.finished_at">
                    结束于 {{ formatDateTime(data.instance.finished_at) }}
                  </span>
                </div>
              </div>
            </Space>

            <!-- 处理按钮放标题栏右上角：进页面第一眼就该看到「我要做什么」 -->
            <Space :size="8" class="header-ops" wrap>
              <ActionPanel
                v-if="showHeaderActions"
                :data="data"
                :field-patch="fieldPatch"
                @acted="load"
                @clear-patch="clearPatch"
              />

              <a-divider
                v-if="showHeaderActions && showInstanceOps"
                type="vertical"
                class="ops-divider"
              />

              <Tag v-if="activeSnapshotId" color="orange" class="snapshot-tag">
                <HistoryOutlined />
                正在查看历史快照
                <a @click="activeSnapshotId = null">退出</a>
              </Tag>
              <Button v-if="canWithdraw" :loading="operating" @click="doWithdraw">
                <template #icon><RollbackOutlined /></template>
                撤回
              </Button>
              <Button v-if="canAbandon" :loading="operating" @click="doAbandon">撤销申请</Button>
              <Button v-if="canTerminate" danger @click="terminateOpen = true">终止</Button>
            </Space>
          </div>

          <div v-if="data.instance.status === 'TERMINATED' && data.instance.terminated_reason" class="terminated">
            终止原因：{{ data.instance.terminated_reason }}
          </div>
        </Card>

        <!-- ------------------------------------------------ 表单 -->
        <Card :bordered="false" class="block">
          <template #title>
            表单信息
            <Tag v-if="activeSnapshotId" color="orange" class="title-tag">
              快照 #{{ data.snapshot?.seq }}（{{ formatDateTime(data.snapshot?.created_at) }}）
            </Tag>
            <Tag v-else-if="canEditForm" color="blue" class="title-tag">
              你可以在本节点修改高亮的字段
            </Tag>
          </template>

          <template #extra>
            <span v-if="Object.keys(fieldPatch).length" class="text-muted changed-hint">
              已改动 {{ Object.keys(fieldPatch).length }} 个字段
            </span>
          </template>

          <FormRenderer
            :schema="data.schema_data"
            :model-value="formValues"
            :permissions="permissions"
            :mode="formMode"
            @update:model-value="onFormChange"
          />
        </Card>

        <!-- ------------------------------------------------ 进度 -->
        <Card title="审批进度" :bordered="false" class="block">
          <ProgressBar
            :nodes="data.progress"
            :active-node-id="data.current_node?.node_id ?? null"
          />
        </Card>

        <!-- ------------------------------------------------ 时间线 -->
        <Card title="处理历史" :bordered="false" class="block">
          <TimelineList
            :actions="data.actions"
            :active-snapshot-id="activeSnapshotId"
            @view-snapshot="viewSnapshot"
          />
        </Card>
      </template>
    </a-spin>

    <Modal
      v-model:open="terminateOpen"
      title="终止流程"
      :confirm-loading="operating"
      ok-text="确认终止"
      cancel-text="取消"
      :ok-button-props="{ danger: true }"
      @ok="doTerminate"
    >
      <a-alert
        type="warning"
        show-icon
        message="终止后所有待办会被取消，实例不可恢复"
        class="mb"
      />
      <a-form-item label="终止原因" required>
        <a-textarea
          v-model:value="terminateReason"
          :rows="3"
          placeholder="必填，会写入审计与通知"
        />
      </a-form-item>
    </Modal>
  </div>
</template>

<style scoped lang="scss">
.header-card {
  border-radius: 8px;
  margin-bottom: 12px;
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.title {
  font-size: 16px;
  font-weight: 600;
}

.meta-line {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 12px;
}

.header-ops {
  align-items: center;
}

.ops-divider {
  margin: 0 2px;
}

.snapshot-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 4px 10px;
}

.terminated {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #fff1f0;
  color: #cf1322;
  font-size: 12px;
}

.block {
  border-radius: 8px;
  margin-bottom: 12px;
}

.title-tag {
  margin-left: 8px;
  font-size: 11px;
}

.changed-hint {
  font-size: 12px;
}

.mb {
  margin-bottom: 12px;
}
</style>

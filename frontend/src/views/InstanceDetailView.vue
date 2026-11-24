<script setup lang="ts">
/**
 * ★ 实例详情页（PRD §5「全部价值的交汇点」）。
 *
 * 版面自上而下：
 *   标题栏  单号/状态/发起人 + **处理按钮**（同意/驳回/退回，仅当前处理人可见）
 *           + 实例级操作（撤回/撤销/终止）
 *   表单    按**服务端下发的权限**渲染的分区表单（hidden 不渲染 / readonly 只读 / editable 可改）
 *   进度/历史  左右两栏：左边进度（并行组并列、条件分支标出实际走向），
 *              右边处理历史（可回放快照）。窄屏自动退化为上下排列。
 *
 * 数据一次取全（`GET /instances/{id}/render`），避免分多次请求拼装导致的撕裂状态。
 */
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  HistoryOutlined,
  PrinterOutlined,
  RollbackOutlined,
} from '@ant-design/icons-vue'
import { Button, Card, Modal, Space, Tag } from 'ant-design-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { instanceApi } from '@/api/modules/instance'
import { userApi } from '@/api/modules/user'
import { FormRenderer } from '@/components/form-renderer'
import ActionPanel from '@/components/instance/ActionPanel.vue'
import ExtFieldManager from '@/components/instance/ExtFieldManager.vue'
import PrintDocument from '@/components/instance/PrintDocument.vue'
import ProgressBar from '@/components/instance/ProgressBar.vue'
import ResubmitPanel from '@/components/instance/ResubmitPanel.vue'
import SnapshotDiff from '@/components/instance/SnapshotDiff.vue'
import TimelineList from '@/components/instance/TimelineList.vue'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import type { FieldState } from '@/types/form'
import type { InstanceRender } from '@/types/instance'
import { INSTANCE_STATUS_META, MY_ROLE_LABELS } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'
import { downloadFile, printPage } from '@/utils/download'
import { feedback } from '@/utils/feedback'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const org = useOrgStore()

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

/** 节点权限矩阵（不含表单联动规则）；规则交给 FormRenderer 随输入重算 */
const permissions = computed<Record<string, FieldState>>(() => {
  const raw = data.value?.base_permissions ?? data.value?.permissions ?? {}
  const out: Record<string, FieldState> = {}
  for (const [key, perm] of Object.entries(raw)) {
    out[key] = { visible: perm.visible, editable: perm.editable, required: perm.required }
  }
  return out
})

const formRules = computed(() => data.value?.form_rules ?? data.value?.schema_data.rules ?? [])

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
    // 只读的人员控件靠 org 缓存换名字；发起人至少先塞进去，
    // 否则「发起人」自动填充字段在详情页会显示成 #id
    if (data.value.instance.initiator_name) {
      org.rememberUsers([
        {
          id: data.value.instance.initiator_id,
          username: '',
          real_name: data.value.instance.initiator_name,
          dept_name: data.value.instance.initiator_dept_name,
        },
      ])
    }
    // 只读表单与打印文档靠 org 缓存把人员 id 换成人名；预取一页人员足够覆盖常见表单
    try {
      const users = await userApi.options({ limit: 200 })
      org.rememberUsers(users)
    } catch {
      // 名字缓存失败不影响单据主数据
    }
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

/** 处理完任务后清掉 URL 上的 assignment，避免刷新/回退时又按旧待办渲染 */
async function onActed(): Promise<void> {
  // 先本地摘掉待办状态：不等 reload 完成，按钮/可编辑态就立即消失
  if (data.value) {
    data.value.assignment = null
    data.value.allowed_actions = []
    data.value.current_node = null
    if (data.value.my_role === 'CURRENT_HANDLER') {
      data.value.my_role = auth.user?.id === data.value.instance.initiator_id
        ? 'INITIATOR'
        : 'PARTICIPANT'
    }
  }
  if (route.query.assignment) {
    await router.replace({ query: { ...route.query, assignment: undefined } })
  }
  await load()
}

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

/**
 * 追加字段入口（F5.1）：管理员/设计者，且实例还在跑。
 *
 * 用 auth store 的 isDesigner 而不是 my_role —— 设计者看自己经手的单子时
 * my_role 是 INITIATOR/PARTICIPANT，只有拿角色才能判断出来（管理员包含在内）。
 * 服务端同样两道校验：看得见 + 管理员/设计者。
 */
const showExtFieldEntry = computed(
  () =>
    auth.isDesigner &&
    !activeSnapshotId.value &&
    !['APPROVED', 'WITHDRAWN', 'TERMINATED'].includes(data.value?.instance.status ?? ''),
)

/** 追加/停用字段后，服务端回的就是刷新过的详情页数据 —— 直接换掉即可 */
function onExtFieldUpdated(fresh: InstanceRender): void {
  data.value = fresh
  clearPatch()
}

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

/** 被驳回且我是发起人 → 可以改单重提（PRD §3.5.1） */
const canResubmit = computed(
  () =>
    !activeSnapshotId.value &&
    data.value?.my_role === 'INITIATOR' &&
    data.value?.instance.status === 'REJECTED',
)

/** 导出（F8.2）：看得见就能导出，权限由服务端按同一条可见性规则判 */
const exporting = ref(false)

async function doExport(): Promise<void> {
  exporting.value = true
  try {
    await downloadFile(
      instanceApi.instanceExportUrl(instanceId.value),
      `${data.value?.instance.code ?? 'instance'}.csv`,
    )
    feedback.success('已开始下载')
  } catch {
    // 拦截器已提示
  } finally {
    exporting.value = false
  }
}
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
                @acted="onActed"
                @clear-patch="clearPatch"
              />

              <a-divider
                v-if="showHeaderActions && showInstanceOps"
                type="vertical"
                class="ops-divider"
              />

              <ExtFieldManager
                v-if="showExtFieldEntry"
                :data="data"
                :can-manage="true"
                @updated="onExtFieldUpdated"
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

              <a-divider type="vertical" class="ops-divider" />
              <Button :loading="exporting" @click="doExport">
                <template #icon><DownloadOutlined /></template>
                导出
              </Button>
              <Button @click="printPage">
                <template #icon><PrinterOutlined /></template>
                打印
              </Button>
            </Space>
          </div>

          <div v-if="data.instance.status === 'TERMINATED' && data.instance.terminated_reason" class="terminated">
            终止原因：{{ data.instance.terminated_reason }}
          </div>
        </Card>

        <!-- ------------------------------------------------ 驳回重提 -->
        <ResubmitPanel v-if="canResubmit" :data="data" @submitted="load" />

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
            :rules="formRules"
            :mode="formMode"
            @update:model-value="onFormChange"
          />
        </Card>

        <!-- ------------------------------------------------ 变更对照（看快照时） -->
        <SnapshotDiff
          v-if="activeSnapshotId"
          :instance-id="instanceId"
          :snapshot-id="activeSnapshotId"
          :actions="data.actions"
          :schema="data.schema_data"
          :attachments="data.attachments"
        />

        <!-- ------------------------------------------------ 进度 + 处理历史 -->
        <div class="progress-history">
          <Card title="审批进度" :bordered="false" class="block">
            <ProgressBar
              :nodes="data.progress"
              :active-node-id="data.current_node?.node_id ?? null"
            />
          </Card>

          <Card title="处理历史" :bordered="false" class="block">
            <TimelineList
              :actions="data.actions"
              :active-snapshot-id="activeSnapshotId"
              :schema="data.schema_data"
              :attachments="data.attachments"
              @view-snapshot="viewSnapshot"
            />
          </Card>
        </div>
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

    <!-- 屏幕隐藏，window.print() 时由全局打印样式显示 -->
    <PrintDocument
      v-if="data"
      :data="data"
      :values="formValues"
      :permissions="permissions"
      :rules="formRules"
    />
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

/* 进度与历史并排：各自独占一行时右侧大片留白，显得松散 */
.progress-history {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  margin-bottom: 12px;

  .block {
    margin-bottom: 0;
  }
}

/* 窄屏放不下两栏时退回上下排列（与原有窄屏样式一致） */
@media (max-width: 992px) {
  .progress-history {
    grid-template-columns: minmax(0, 1fr);
  }
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

@media (max-width: 768px) {
  .header-row {
    flex-direction: column;
    align-items: stretch;
  }

  .header-ops {
    flex-wrap: wrap;
  }

  .header-card :deep(.ant-card-body),
  .block :deep(.ant-card-body) {
    padding: 12px;
  }

  .title {
    font-size: 15px;
  }
}
</style>

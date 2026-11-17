<script setup lang="ts">
/**
 * 发起填写页（F3.2 / F3.3 / F3.4 / F3.5）。
 *
 * - 按**发起节点的字段权限**渲染：`visible_at_start=false` 的补充字段此阶段完全不出现
 * - 自动暂存：改动後 2s 落草稿（F3.3「自动暂存」），不生成审批任务
 * - 流程含「发起人指定审批人」的节点时，提交前先选人（F3.5）
 */
import { ArrowLeftOutlined, CheckOutlined, SaveOutlined, UserSwitchOutlined } from '@ant-design/icons-vue'
import { Button, Card, Modal, Space, Tag } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { instanceApi } from '@/api/modules/instance'
import { userApi } from '@/api/modules/user'
import { FormRenderer } from '@/components/form-renderer'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import type { FieldState } from '@/types/form'
import type { StartOptions } from '@/types/instance'
import { applyFormRules } from '@/utils/formRules'
import { buildInitialValues, validateValues } from '@/utils/formValue'
import { feedback } from '@/utils/feedback'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const org = useOrgStore()

const flowTemplateId = computed(() => Number(route.params.flowTemplateId))
const draftId = computed(() => {
  const raw = route.query.draftId
  return raw ? Number(raw) : null
})

const options = ref<StartOptions | null>(null)
const instanceId = ref<number | null>(null)
const values = ref<Record<string, unknown>>({})
const loading = ref(false)
const submitting = ref(false)
const saving = ref(false)
const lastSavedAt = ref<Date | null>(null)
const dirty = ref(false)

const permissions = computed<Record<string, FieldState>>(() => {
  const raw: Record<string, FieldState> = {}
  const source = options.value?.base_permissions ?? options.value?.permissions ?? {}
  for (const [key, perm] of Object.entries(source)) {
    raw[key] = { visible: perm.visible, editable: perm.editable, required: perm.required }
  }
  return raw
})

const formRules = computed(
  () => options.value?.form_rules ?? options.value?.schema_data.rules ?? [],
)

const needsAssigneePick = computed(() => (options.value?.initiator_select_nodes.length ?? 0) > 0)

/** 表单已发布新版本，但流程还锁着旧版：字段/可见性等改动尚未生效 */
const formOutdated = computed(() => {
  const latest = options.value?.form_latest_version_no
  const used = options.value?.form_version_no
  return latest != null && used != null && latest > used
})

// --------------------------------------------------------------------------- 加载

async function load(): Promise<void> {
  loading.value = true
  try {
    options.value = await instanceApi.startOptions(flowTemplateId.value)

    // 自动填充的人员控件是只读展示，靠 org 缓存把 id 换成人名
    if (auth.user) {
      org.rememberUsers([
        { id: auth.user.id, username: auth.user.username, real_name: auth.user.real_name },
      ])
    }

    const initial = {
      ...buildInitialValues(options.value.schema_data),
      ...(options.value.default_values ?? {}),
      ...(options.value.auto_fill_values ?? {}),
    }

    if (draftId.value) {
      // 续填：草稿值优先于默认值/自动填充值（草稿里已经落过库）
      const drafts = await instanceApi.listDrafts()
      const draft = drafts.find((d) => d.id === draftId.value)
      if (draft) {
        instanceId.value = draft.id
        const all = await instanceApi.render(draft.id)
        values.value = { ...initial, ...all.values }
        return
      }
    }
    values.value = initial
  } catch (error) {
    if (error instanceof ApiError) feedback.error(error.message)
    await router.replace({ name: 'start-center' })
  } finally {
    loading.value = false
  }
}

onMounted(load)

// --------------------------------------------------------------------------- 自动暂存

let saveTimer: ReturnType<typeof setTimeout> | null = null

function onFormChange(next: Record<string, unknown>): void {
  values.value = next
  dirty.value = true
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void saveDraft(true), 2000)
}

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})

/** 同一时刻只允许一个暂存请求：自动暂存和提交可能同时触发，否则会建出两份草稿。 */
let draftSaving: Promise<void> | null = null

async function saveDraft(quiet = false): Promise<void> {
  if (!options.value) return
  if (draftSaving) {
    await draftSaving
    return
  }
  // 首次提交时即使没有改动也要先建草稿；已有草稿且无改动则跳过
  if (instanceId.value !== null && !dirty.value) return

  const task = doSaveDraft(quiet)
  draftSaving = task
  try {
    await task
  } finally {
    if (draftSaving === task) draftSaving = null
  }
}

/** 自动编号字段的 key（服务端在首次暂存时分配） */
function autoNumberKeys(): string[] {
  const keys: string[] = []
  for (const section of options.value?.schema_data.sections ?? []) {
    for (const field of section.fields) {
      if (field.auto_number) keys.push(field.key)
    }
  }
  return keys
}

/** 首次暂存后把服务端生成的编号带回到表单（只补空值，不覆盖用户改动） */
async function mergeAutoNumbers(id: number): Promise<void> {
  const keys = autoNumberKeys()
  const empty = keys.filter((key) => {
    const value = values.value[key]
    return value === undefined || value === null || value === ''
  })
  if (!empty.length) return
  try {
    const full = await instanceApi.render(id)
    const next = { ...values.value }
    for (const key of keys) {
      const value = full.values[key]
      if (value !== undefined && value !== null && value !== '') next[key] = value
    }
    values.value = next
  } catch {
    // 编号已经落库，下次刷新/暂存还能取到；这里失败不打断填写
  }
}

async function doSaveDraft(quiet: boolean): Promise<void> {
  saving.value = true
  try {
    if (instanceId.value === null) {
      const created = await instanceApi.createDraft({
        flow_template_id: flowTemplateId.value,
        data: values.value,
      })
      instanceId.value = created.id
      await mergeAutoNumbers(created.id)
    } else {
      await instanceApi.updateDraft(instanceId.value, { data: values.value })
      await mergeAutoNumbers(instanceId.value)
    }
    lastSavedAt.value = new Date()
    dirty.value = false
    if (!quiet) feedback.success('已暂存')
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

// --------------------------------------------------------------------------- 提交

const pickModalOpen = ref(false)
const pickAssignees = ref<Record<string, number[]>>({})
const candidateUsers = ref<Array<{ value: number; label: string }>>([])

/** 表单校验失败时把问题指明给用户，而不是让后端 400 回来 */
function localIssues() {
  if (!options.value) return []
  const states = applyFormRules(permissions.value, formRules.value, values.value)
  return validateValues(options.value.schema_data, values.value, states)
}

async function prepareSubmit(): Promise<void> {
  if (submitting.value) return
  const issues = localIssues()
  if (issues.length) {
    feedback.error(`还有必填项未完成：${issues.slice(0, 3).map((i) => i.label).join('、')}`)
    return
  }

  if (needsAssigneePick.value) {
    // 拉候选人（简化实现：给全部启用用户；精确范围由服务端的 scope 决定）
    const users = await userApi.options({ limit: 200 })
    candidateUsers.value = users.map((u) => ({ value: u.id, label: `${u.real_name}（${u.username}）` }))
    pickModalOpen.value = true
    return
  }

  await doSubmit({})
}

async function doSubmit(picks: Record<string, number[]>): Promise<void> {
  if (!options.value || submitting.value) return
  // 从建草稿开始就进入提交态：连点两次提交不会再发一轮请求
  submitting.value = true
  try {
    // 先确保草稿已落库（没有草稿则先建）
    await saveDraft(true)
    if (instanceId.value === null) {
      feedback.error('暂存失败，请重试')
      return
    }

    const result = await instanceApi.submit(instanceId.value, {
      data: values.value,
      assignee_picks: picks,
    })
    feedback.success('已提交，流程开始流转')
    await router.replace({ name: 'instance-detail', params: { id: result.id } })
  } catch (error) {
    if (error instanceof ApiError) feedback.error(error.message)
  } finally {
    submitting.value = false
  }
}

function confirmPicks(): void {
  const missing = (options.value?.initiator_select_nodes ?? []).filter(
    (n) => !pickAssignees.value[n.node_id]?.length,
  )
  if (missing.length) {
    feedback.error(`请为「${missing[0].node_name}」选择审批人`)
    return
  }
  pickModalOpen.value = false
  void doSubmit(pickAssignees.value)
}
</script>

<template>
  <div class="page-container">
    <a-spin :spinning="loading">
      <template v-if="options">
        <a-alert
          v-if="formOutdated && (auth.isAdmin || auth.isDesigner)"
          type="warning"
          show-icon
          class="block"
          message="流程仍在使用旧版表单"
          :description="`当前锁定表单 v${options.form_version_no}，最新已发布 v${options.form_latest_version_no}。表单的字段、校验、发起阶段可见性等改动，需要设计者重新发布流程后才会生效。`"
        />

        <Card :bordered="false" class="block" :body-style="{ padding: '12px 18px' }">
          <div class="header">
            <Space>
              <Button type="text" @click="router.push({ name: 'start-center' })">
                <template #icon><ArrowLeftOutlined /></template>
              </Button>
              
              <!-- <Tag color="green">流程 v{{ options.flow_version_no }}</Tag>
              <Tag color="blue">表单 v{{ options.form_version_no }}</Tag> -->
            </Space>

            <Space>
              <span class="text-muted save-hint">
                <template v-if="saving">暂存中…</template>
                <template v-else-if="dirty">有未保存的改动</template>
                <template v-else-if="lastSavedAt">已暂存</template>
              </span>
              <Button :loading="saving" @click="saveDraft(false)">
                <template #icon><SaveOutlined /></template>
                暂存
              </Button>
              <Button
                type="primary"
                :loading="submitting"
                @click="prepareSubmit"
              >
                <template #icon><CheckOutlined /></template>
                提交
              </Button>
            </Space>
          </div>

        </Card>

        <Card :bordered="false" class="block form-block">

          <div class="title">
            <span>{{ options.flow_template_name }}</span>
          </div>
        
          <FormRenderer
            :schema="options.schema_data"
            :model-value="values"
            :permissions="permissions"
            :rules="formRules"
            mode="edit"
            @update:model-value="onFormChange"
          />
        </Card>

        <div class="footer-actions">
          <Button size="large" @click="saveDraft(false)">暂存草稿</Button>
          <Button type="primary" size="large" :loading="submitting" @click="prepareSubmit">
            提交审批
          </Button>
        </div>
      </template>
    </a-spin>

    <!-- ------------------------------------------------ 发起人指定审批人（F3.5） -->
    <Modal
      v-model:open="pickModalOpen"
      title="指定审批人"
      :confirm-loading="submitting"
      ok-text="确认并提交"
      cancel-text="返回修改"
      @ok="confirmPicks"
    >
      <a-alert
        type="info"
        show-icon
        class="mb"
        message="该流程有节点需要你指定审批人，请选择后再提交"
      />
      <a-form-item
        v-for="node in options?.initiator_select_nodes ?? []"
        :key="node.node_id"
        :label="node.node_name"
        required
      >
        <a-select
          v-model:value="pickAssignees[node.node_id]"
          :options="candidateUsers"
          mode="multiple"
          placeholder="选择审批人"
          show-search
          option-filter-prop="label"
        />
      </a-form-item>
      <div class="text-muted tiny">
        <UserSwitchOutlined />
        候选人范围由流程配置决定
      </div>
    </Modal>
  </div>
</template>

<style scoped lang="scss">
.block {
  border-radius: 8px;
  margin-bottom: 12px;
}

.form-block {
  border: 1px solid #cccddd;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.title {
  text-align: center;
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 20px;
}

.save-hint {
  font-size: 12px;
}

.footer-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 8px 0 24px;
}

.mb {
  margin-bottom: 12px;
}

.tiny {
  font-size: 11px;
}

@media (max-width: 768px) {
  .footer-actions {
    position: sticky;
    bottom: 0;
    z-index: 5;
    padding: 10px 0;
    background: #f5f6f8;
  }
}
</style>

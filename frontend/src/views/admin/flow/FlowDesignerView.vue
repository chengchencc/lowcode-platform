<script setup lang="ts">
/**
 * 流程配置器（F2.1–F2.7）。
 *
 * 布局：左侧节点清单树 + 右侧属性面板。
 * PRD §5 提到「顶部实时预览」，流程的预览是进度条形态、依赖实例数据，
 * 放在 M4 的实例详情页更合适，这里不做占位。
 *
 * 保存策略与表单配置器一致：改动后 1.5s 防抖自动保存，
 * **保存不做语义校验**（后端刻意如此），发布时才拦。
 */
import {
  ArrowDownOutlined,
  ArrowLeftOutlined,
  ArrowUpOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'
import { Button, Card, Empty, Space, Tag, Tooltip } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { flowApi } from '@/api/modules/flow'
import { formApi } from '@/api/modules/form'
import { userApi } from '@/api/modules/user'
import FlowCanvas from '@/components/flow-designer/canvas/FlowCanvas.vue'
import {
  ADDABLE_NODES,
  findLocation,
  findNode,
  makeNode,
  moveWithinSiblings,
  removeNode,
  type AddableNodeType,
} from '@/components/flow-designer/definitionOps'
import NodePropertyPanel from '@/components/flow-designer/NodePropertyPanel.vue'
import { useOrgStore } from '@/stores/org'
import type { FormSchema } from '@/types/form'
import type {
  FlowDefinition,
  FlowTemplate,
  FlowValidateResult,
  FlowVersion,
  ParallelNode,
  ReturnTarget,
  StepNode,
} from '@/types/flow'
import { NODE_TYPE_LABELS } from '@/types/flow'
import { feedback } from '@/utils/feedback'

const route = useRoute()
const router = useRouter()
const org = useOrgStore()

const templateId = computed(() => Number(route.params.id))

const template = ref<FlowTemplate | null>(null)
const version = ref<FlowVersion | null>(null)
const definition = ref<FlowDefinition | null>(null)
const formSchema = ref<FormSchema | null>(null)

const loading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const dirty = ref(false)
const lastSavedAt = ref<Date | null>(null)

const selectedId = ref<string | null>(null)
const viewMode = ref<'canvas' | 'list'>('canvas')
const returnTargets = ref<ReturnTarget[]>([])
const userOptions = ref<Array<{ value: number; label: string }>>([])

// --------------------------------------------------------------------------- 加载

async function load(): Promise<void> {
  loading.value = true
  try {
    template.value = await flowApi.getTemplate(templateId.value)

    let target: FlowVersion
    if (template.value.draft_version_id) {
      target = await flowApi.getVersion(template.value.draft_version_id)
    } else {
      target = await flowApi.createVersion(templateId.value)
    }
    version.value = target
    definition.value = normalizeDefinition(target.definition)

    // 绑定的表单 schema —— 字段权限矩阵与条件编辑器都要用
    const formVersion = await formApi.getVersion(target.locked_form_version_id)
    formSchema.value = formVersion.schema_data

    await Promise.all([org.loadRoles(), org.loadDeptTree(), loadUserOptions()])
    selectedId.value = definition.value.steps[0]?.id ?? null
  } finally {
    loading.value = false
  }
}

/** 后端保证结构完整，这里只兜底缺省字段，避免面板读到 undefined */
function normalizeDefinition(input: FlowDefinition): FlowDefinition {
  const def: FlowDefinition = {
    model_version: input.model_version ?? 1,
    start: input.start ?? { id: 'start', type: 'start', name: '发起', fields_permission: null },
    steps: (input.steps ?? []).map(normalizeStep),
    end: input.end ?? { id: 'end', type: 'end', name: '结束' },
  }
  return def
}

function normalizeStep(step: StepNode): StepNode {
  if (step.type === 'approval' || step.type === 'fill') {
    step.assignee ??= { mode: 'SINGLE', sources: [] }
    step.assignee.sources ??= []
    step.return_targets ??= null
    step.fields_permission ??= {
      base: 'readonly', partitions: {}, overrides: {}, conditional_overrides: [],
    }
  }
  if (step.type === 'condition') {
    step.branches ??= []
    for (const branch of step.branches) {
      branch.steps = (branch.steps ?? []).map(normalizeStep)
    }
  }
  if (step.type === 'parallel') {
    step.members = (step.members ?? []).map(normalizeStep) as ParallelNode['members']
  }
  if (step.type === 'cc') {
    step.cc_to ??= { mode: 'SINGLE', sources: [] }
    step.cc_to.sources ??= []
  }
  return step
}

async function loadUserOptions(): Promise<void> {
  const users = await userApi.options({ limit: 200 })
  userOptions.value = users.map((u) => ({ value: u.id, label: `${u.real_name}（${u.username}）` }))
}

onMounted(load)

// --------------------------------------------------------------------------- 自动保存

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  dirty.value = true
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void save(), 1500)
}

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})

async function save(): Promise<boolean> {
  if (!version.value || !definition.value || !dirty.value) return true
  saving.value = true
  try {
    version.value = await flowApi.saveVersion(version.value.id, definition.value)
    lastSavedAt.value = new Date()
    dirty.value = false
    return true
  } catch (error) {
    if (error instanceof ApiError) feedback.error(error.message)
    return false
  } finally {
    saving.value = false
  }
}

function onNodeChange(): void {
  scheduleSave()
  void refreshReturnTargets()
}

// --------------------------------------------------------------------------- 节点查找

const selectedNode = computed(() =>
  definition.value && selectedId.value
    ? findNode(definition.value, selectedId.value)
    : null,
)

/** 所有节点的 id→名称，供「上一节点处理人」的候选下拉 */
const nodeNameById = computed(() => {
  const out: Record<string, string> = {}
  const walk = (steps: StepNode[]) => {
    for (const step of steps) {
      out[step.id] = step.name
      if (step.type === 'condition') step.branches.forEach((b) => walk(b.steps))
      if (step.type === 'parallel') walk(step.members as StepNode[])
    }
  }
  if (definition.value) walk(definition.value.steps)
  return out
})

const roleOptions = computed(() => org.roles.map((r) => ({ value: r.id, label: r.name })))

async function refreshReturnTargets(): Promise<void> {
  if (!version.value || !selectedNode.value) {
    returnTargets.value = []
    return
  }
  const node = selectedNode.value
  if (node.type !== 'approval' && node.type !== 'fill') {
    returnTargets.value = []
    return
  }
  try {
    returnTargets.value = await flowApi.returnTargets(version.value.id, node.id)
  } catch {
    // 节点可能刚被新增、还没保存过 —— 静默即可，下次改动会再试
    returnTargets.value = []
  }
}

watch(selectedId, () => void refreshReturnTargets())

// --------------------------------------------------------------------------- 增删节点

function addNode(type: AddableNodeType, into?: StepNode[]): void {
  if (!definition.value) return
  const node = makeNode(definition.value, type)
  ;(into ?? definition.value.steps).push(node)
  selectedId.value = node.id
  scheduleSave()
}

function deleteSelected(): void {
  const id = selectedId.value
  if (!id || !definition.value) return
  const node = findNode(definition.value, id)
  if (!node) return
  if (!window.confirm(`删除节点「${node.name}」？其中配置的审批人与字段权限会一并移除。`)) return
  if (removeNode(definition.value, id)) {
    selectedId.value = definition.value.steps[0]?.id ?? null
    scheduleSave()
  }
}

function moveSelected(delta: number): void {
  const id = selectedId.value
  if (!id || !definition.value) return
  const location = findLocation(definition.value, id)
  if (!location) return
  if (moveWithinSiblings(definition.value, id, location.index + delta)) scheduleSave()
}

// --------------------------------------------------------------------------- 校验与发布

const validateOpen = ref(false)
const validateResult = ref<FlowValidateResult | null>(null)

async function runValidate(): Promise<void> {
  if (!(await save())) return
  validateResult.value = await flowApi.validateVersion(version.value!.id)
  validateOpen.value = true
}

async function publish(): Promise<void> {
  if (!(await save())) return

  const result = await flowApi.validateVersion(version.value!.id)
  if (!result.valid) {
    validateResult.value = result
    validateOpen.value = true
    feedback.error('还有错误未修复，无法发布')
    return
  }

  const ok = await feedback.confirm({
    title: `发布 v${version.value!.version_no}？`,
    content: '发布后该版本冻结，并锁定当前表单版本；后续改动需新建版本。',
  })
  if (!ok) return

  publishing.value = true
  try {
    await flowApi.publishVersion(version.value!.id)
    feedback.success('已发布')
    await load()
  } catch (error) {
    if (error instanceof ApiError) feedback.error(error.message)
  } finally {
    publishing.value = false
  }
}

const readonly = computed(() => version.value?.status !== 'DRAFT')

const versionLabel = computed(() => {
  if (!version.value) return ''
  const status = version.value.status
  const text = status === 'DRAFT' ? '草稿' : status === 'PUBLISHED' ? '已发布' : '已归档'
  return `v${version.value.version_no} · ${text}`
})

/** 节点在树上的层级，用于缩进 */
interface TreeItem {
  node: StepNode
  depth: number
  /** 所属容器（条件分支或并行组），用于「添加同级节点」 */
  container?: StepNode[]
  branchLabel?: string
}

const treeItems = computed<TreeItem[]>(() => {
  const out: TreeItem[] = []
  const walk = (steps: StepNode[], depth: number, container: StepNode[], branchLabel?: string) => {
    for (const step of steps) {
      out.push({ node: step, depth, container, branchLabel })
      if (step.type === 'condition') {
        for (const branch of step.branches) {
          walk(branch.steps, depth + 1, branch.steps, branch.name || branch.id)
        }
      }
      if (step.type === 'parallel') {
        walk(step.members as StepNode[], depth + 1, step.members as StepNode[], step.name)
      }
    }
  }
  if (definition.value) walk(definition.value.steps, 0, definition.value.steps)
  return out
})
</script>

<template>
  <div class="page-container designer">
    <Card :bordered="false" class="designer-header" :body-style="{ padding: '12px 16px' }">
      <div class="header-row">
        <Space>
          <Button type="text" @click="router.push({ name: 'flow-templates' })">
            <template #icon><ArrowLeftOutlined /></template>
          </Button>
          <span class="title">{{ template?.name }}</span>
          <Tag :color="version?.status === 'PUBLISHED' ? 'green' : 'orange'">{{ versionLabel }}</Tag>
          <Tag v-if="readonly" color="red">已冻结，不可编辑</Tag>
          <Tag v-if="template?.locked_form_version_no" color="blue">
            锁定表单 v{{ template.locked_form_version_no }}
          </Tag>
          <a-radio-group v-model:value="viewMode" size="small" button-style="solid">
            <a-radio-button value="canvas">画布</a-radio-button>
            <a-radio-button value="list">清单</a-radio-button>
          </a-radio-group>
        </Space>

        <Space>
          <span class="text-muted save-hint">
            <template v-if="saving">保存中…</template>
            <template v-else-if="dirty">有未保存的改动</template>
            <template v-else-if="lastSavedAt">已保存</template>
          </span>
          <Button :disabled="readonly" :loading="saving" @click="save">
            <template #icon><SaveOutlined /></template>
            保存
          </Button>
          <Button @click="runValidate">
            <template #icon><CheckCircleOutlined /></template>
            校验
          </Button>
          <!-- 只用 readonly 做禁用：设计器有自动保存，dirty 会很快变回 false，
               用它做条件会让按钮在保存后立刻变灰。publish() 内部会先 save()。 -->
          <Button
            type="primary"
            :disabled="readonly"
            :loading="publishing"
            @click="publish"
          >
            发布
          </Button>
        </Space>
      </div>
    </Card>

    <a-row :gutter="16" class="designer-body">
      <!-- ------------------------------------------------ 左侧：画布 / 节点清单 -->
      <a-col :xs="24" :md="viewMode === 'canvas' ? 16 : 9" :lg="viewMode === 'canvas' ? 17 : 7">
        <Card
          v-if="viewMode === 'canvas'"
          :bordered="false"
          :loading="loading"
          class="panel canvas-panel"
        >
          <FlowCanvas
            v-if="definition"
            v-model:selected-id="selectedId"
            :definition="definition"
            :readonly="readonly"
            @change="onNodeChange"
          />
          <a-empty v-else description="还没有流程定义" />
        </Card>

        <Card v-else :bordered="false" :loading="loading" class="panel">
          <template #title>流程节点</template>

          <a-empty v-if="!treeItems.length" description="还没有节点" />

          <div
            v-for="item in treeItems"
            :key="item.node.id"
            class="node-item"
            :class="{ active: selectedId === item.node.id }"
            :style="{ paddingLeft: `${8 + item.depth * 16}px` }"
            @click="selectedId = item.node.id"
          >
            <span class="node-type">{{ NODE_TYPE_LABELS[item.node.type] }}</span>
            <span class="node-name">{{ item.node.name }}</span>
            <span class="spacer" />
            <Tooltip title="上移">
              <Button type="text" size="small" @click.stop="moveSelected(-1)">
                <template #icon><ArrowUpOutlined /></template>
              </Button>
            </Tooltip>
            <Tooltip title="下移">
              <Button type="text" size="small" @click.stop="moveSelected(1)">
                <template #icon><ArrowDownOutlined /></template>
              </Button>
            </Tooltip>
            <Tooltip title="删除">
              <Button type="text" size="small" danger @click.stop="deleteSelected">
                <template #icon><DeleteOutlined /></template>
              </Button>
            </Tooltip>
          </div>

          <a-divider style="margin: 12px 0" />

          <div class="add-row">
            <a-dropdown :trigger="['click']">
              <Button type="dashed" block size="small" :disabled="readonly">
                <template #icon><PlusOutlined /></template>
                添加到主线
              </Button>
              <template #overlay>
                <a-menu>
                  <a-menu-item
                    v-for="opt in ADDABLE_NODES"
                    :key="opt.type"
                    @click="addNode(opt.type)"
                  >
                    {{ opt.label }}
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>

          <!-- 往当前条件的某个分支 / 并行组里加节点 -->
          <template v-if="selectedNode && (selectedNode.type === 'condition' || selectedNode.type === 'parallel')">
            <div class="text-muted tiny mt">
              <template v-if="selectedNode.type === 'condition'">
                向分支添加：点左侧分支下已有的节点，或用下面的按钮加到第 1 个分支
              </template>
              <template v-else>向并行组添加成员：</template>
            </div>
            <a-dropdown :trigger="['click']" class="mt-sm">
              <Button type="dashed" block size="small" :disabled="readonly">
                <template #icon><PlusOutlined /></template>
                {{ selectedNode.type === 'parallel' ? '添加组成员' : '添加到分支' }}
              </Button>
              <template #overlay>
                <a-menu>
                  <a-menu-item
                    v-for="opt in selectedNode.type === 'parallel'
                      ? ADDABLE_NODES.filter((a) => a.type === 'approval' || a.type === 'fill')
                      : ADDABLE_NODES.filter((a) => a.type !== 'parallel')"
                    :key="opt.type"
                    @click="
                      addNode(
                        opt.type,
                        selectedNode.type === 'parallel'
                          ? (selectedNode.members as StepNode[])
                          : (selectedNode as Extract<StepNode, { type: 'condition' }>).branches[0]?.steps,
                      )
                    "
                  >
                    {{ opt.label }}
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </Card>
      </a-col>

      <!-- ------------------------------------------------ 右侧属性面板 -->
      <a-col :xs="24" :md="viewMode === 'canvas' ? 8 : 15" :lg="viewMode === 'canvas' ? 7 : 17">
        <Card :bordered="false" class="panel">
          <template #title>
            <template v-if="selectedNode">
              节点属性：{{ selectedNode.name }}
              <Tag class="type-tag">{{ NODE_TYPE_LABELS[selectedNode.type] }}</Tag>
            </template>
            <template v-else>节点属性</template>
          </template>

          <NodePropertyPanel
            v-if="selectedNode"
            :node="selectedNode"
            :form-schema="formSchema"
            :role-options="roleOptions"
            :user-options="userOptions"
            :return-targets="returnTargets"
            :node-name-by-id="nodeNameById"
            @change="onNodeChange"
          />

          <Empty v-else description="从左侧选择一个节点开始配置" />
        </Card>
      </a-col>
    </a-row>

    <!-- ------------------------------------------------ 校验结果 -->
    <a-drawer v-model:open="validateOpen" title="流程校验" :width="560" placement="right">
      <template v-if="validateResult">
        <a-alert
          :type="validateResult.valid ? 'success' : 'error'"
          show-icon
          :message="
            validateResult.valid
              ? '没有阻断性问题，可以发布'
              : `发现 ${validateResult.errors.length} 个错误，无法发布`
          "
          style="margin-bottom: 16px"
        />
        <div v-if="validateResult.errors.length">
          <h4>错误</h4>
          <ul class="issue-list">
            <li v-for="(issue, i) in validateResult.errors" :key="i">
              <span class="issue-code">{{ issue.code }}</span>
              {{ issue.message }}
              <div v-if="issue.node_id" class="text-muted path">
                节点：{{ nodeNameById[issue.node_id] ?? issue.node_id }}
              </div>
            </li>
          </ul>
        </div>
        <div v-if="validateResult.warnings.length">
          <h4>提示</h4>
          <ul class="issue-list warn">
            <li v-for="(issue, i) in validateResult.warnings" :key="i">
              <span class="issue-code warn">{{ issue.code }}</span>
              {{ issue.message }}
            </li>
          </ul>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<style scoped lang="scss">
.designer-header {
  margin-bottom: 12px;
  border-radius: 8px;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.title {
  font-size: 16px;
  font-weight: 600;
}

.save-hint {
  font-size: 12px;
}

.type-tag {
  font-size: 11px;
  margin-left: 6px;
}

.designer-body {
  align-items: flex-start;
}

.panel {
  border-radius: 8px;
  min-height: 520px;

  :deep(.ant-card-body) {
    padding: 12px;
  }
}

.canvas-panel {
  min-height: 640px;

  :deep(.ant-card-body) {
    padding: 8px;
  }
}

.node-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;

  &:hover {
    background: #fafafa;
  }

  &.active {
    background: #e6f4ff;
  }
}

.node-type {
  flex: 0 0 auto;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #f0f0f0;
  color: rgba(0, 0, 0, 0.55);
}

.node-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spacer {
  flex: 1;
}

.tiny {
  font-size: 11px;
}

.mt {
  margin-top: 10px;
}

.mt-sm {
  margin-top: 6px;
}

.issue-list {
  padding-left: 18px;
  margin: 8px 0 16px;

  li {
    margin-bottom: 8px;
    font-size: 13px;
  }
}

.issue-code {
  display: inline-block;
  padding: 0 5px;
  margin-right: 6px;
  border-radius: 3px;
  background: #fff1f0;
  color: #cf1322;
  font-size: 11px;
  font-family: monospace;

  &.warn {
    background: #fffbe6;
    color: #d48806;
  }
}

.path {
  font-size: 11px;
}
</style>

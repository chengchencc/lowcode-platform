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
  RobotOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'
import { Button, Card, Empty, Space, Tag, Tooltip } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { flowApi } from '@/api/modules/flow'
import { formApi } from '@/api/modules/form'
import { userApi } from '@/api/modules/user'
import AiGenerateModal from '@/components/ai/AiGenerateModal.vue'
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
const aiOpen = ref(false)
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
    if (target.status === 'DRAFT') target = await bindLatestFormVersion(target)
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

/**
 * 草稿版跟随表单的**最新发布版本**。
 *
 * 发布流程时后端本来就会锁到「表单当前发布版本」；设计期如果还绑着旧版本，
 * 表单里新增的字段在审批人、条件、字段权限面板里都选不到。
 * 只动草稿版，已发布版本仍保持它发布时锁定的表单版本。
 */
async function bindLatestFormVersion(target: FlowVersion): Promise<FlowVersion> {
  if (!template.value) return target
  const versions = await formApi.listVersions(template.value.form_template_id)
  const latest = versions
    .filter((v) => v.status === 'PUBLISHED')
    .sort((a, b) => b.version_no - a.version_no)[0]
  if (!latest || latest.id === target.locked_form_version_id) return target
  // 已绑定的版本更新（极少见）时不要往回退
  if (latest.version_no <= (target.locked_form_version_no ?? 0)) return target
  return flowApi.saveVersion(target.id, target.definition, {
    locked_form_version_id: latest.id,
  })
}

/** 后端保证结构完整，这里只兜底缺省字段，避免面板读到 undefined */
function applyAiDefinition(generated: unknown): void {
  const data = generated as FlowDefinition
  if (definition.value?.steps.length) {
    void feedback
      .confirm({
        title: '覆盖当前流程定义？',
        content: 'AI 生成结果会替换当前草稿的节点。',
        danger: true,
      })
      .then((ok) => {
        if (ok) doApplyAiDefinition(data)
      })
    return
  }
  doApplyAiDefinition(data)
}

function doApplyAiDefinition(data: FlowDefinition): void {
  definition.value = normalizeDefinition(data)
  selectedId.value = definition.value.steps[0]?.id ?? null
  scheduleSave()
  feedback.success('已应用到设计器，请检查后保存/发布')
}

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

  // 轻量形状预检 —— 后端 Pydantic 会硬拒空 id / 空 name。
  // 设计期把 id 删空属于"正在编辑中"，不该触发保存、更不该弹 toast。
  const shapeError = checkDefinitionShape(definition.value)
  if (shapeError) return true // 假装保存成功，不清 dirty —— 等用户补完再存

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

/** 后端 Pydantic 形状校验（id/min_length=1 等）的前端兜底预查。
 *  返回 null 表示通过；否则返回简短原因。
 *  只拦硬性形状错误，语义问题（审批人没选、条件没配）留给后端发布时拦。 */
function checkDefinitionShape(def: FlowDefinition): string | null {
  const walk = (steps: StepNode[]): string | null => {
    for (const s of steps) {
      if (!s.id?.trim()) return `节点标识不能为空`
      if (!s.name?.trim()) return `节点名称不能为空`
      if (s.type === 'condition') {
        for (const b of s.branches) {
          const err = walk(b.steps)
          if (err) return err
        }
      } else if (s.type === 'parallel') {
        const err = walk(s.members as StepNode[])
        if (err) return err
      }
    }
    return null
  }
  return walk(def.steps)
}

function onNodeChange(): void {
  // 节点属性任何改动都会来这里，包括改 node.id。
  // 绝对不要在这里手动同步 selectedId ——
  //   - 改 id 时 findNode(def, newId) 可能找不到（空字符串）或找错
  //     （临时冲突），同步 selectedId 会让 selectedNode computed 找不到
  //     对应节点，导致面板消失。
  //   - selectedNode computed 里的缓存回退已经能处理"id 还没同步 /
  //     冲突 / 空值"这些中间态，它依赖的是对象引用而不是 id 字符串。
  scheduleSave()
  void refreshReturnTargets()
}

// --------------------------------------------------------------------------- 节点查找

/** findNode(definition, selectedId) 失败时回退到的缓存引用。
 *  场景：用户正在改 node.id，新 id 还没同步到 selectedId 或者已经与
 *  其他节点冲突（definition 暂时有两个同 id 的节点）——这时 findNode
 *  找不到或找错，面板不能消失。缓存的是**对象引用**，不是 id。 */
const _cachedSelectedNode = ref<StepNode | null>(null)

/** 判断某个 StepNode 引用是否还在 definition 里（递归遍历）。 */
function isNodeInDefinition(def: FlowDefinition, target: StepNode): boolean {
  const walk = (steps: StepNode[]): boolean => {
    for (const s of steps) {
      if (s === target) return true
      if (s.type === 'condition') {
        for (const b of s.branches) if (walk(b.steps)) return true
      } else if (s.type === 'parallel') {
        if (walk(s.members as StepNode[])) return true
      }
    }
    return false
  }
  return walk(def.steps)
}

const selectedNode = computed(() => {
  if (!definition.value || !selectedId.value) {
    _cachedSelectedNode.value = null
    return null
  }
  const found = findNode(definition.value, selectedId.value)
  if (found) {
    _cachedSelectedNode.value = found
    return found
  }
  // findNode 失败（id 刚改了还没同步 / 冲突）→ 用缓存的引用。
  // 注意：缓存的是对象引用，它的 id 可能已经变了，不能再用 id 查找 ——
  // 直接用引用比较确认它还在 definition 里。
  const cached = _cachedSelectedNode.value
  if (cached && isNodeInDefinition(definition.value, cached)) {
    return cached
  }
  return null
})

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
  if (definition.value) {
    // 发起节点也列出来：「上一节点处理人」可以把首个审批节点指派给发起人
    out[definition.value.start.id] = '发起人'
    walk(definition.value.steps)
  }
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
          <Tag v-if="version?.locked_form_version_no" color="blue">
            设计表单 v{{ version.locked_form_version_no }}
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
          <Button @click="aiOpen = true">
            <template #icon><RobotOutlined /></template>
            AI 生成
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

    <AiGenerateModal
      v-model:open="aiOpen"
      kind="flow"
      :form-schema="formSchema"
      @generated="applyAiDefinition"
    />

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

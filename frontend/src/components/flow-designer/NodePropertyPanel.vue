<script setup lang="ts">
/**
 * 节点属性面板（F2.2 / F2.3 / F2.4）。
 *
 * 按节点类型裁剪可见的配置项 —— 给条件节点看「审批人模式」是噪声。
 *
 * 「可退回目标」的候选集**由服务端算**（`/flow-versions/{id}/return-targets`），
 * 前端不重复实现「哪些节点算前序」的规则，避免两边漂移。
 */
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed, onMounted, reactive } from 'vue'

import FieldPermissionPanel from '@/components/flow-designer/FieldPermissionPanel.vue'
import { useOrgStore } from '@/stores/org'
import type { FieldDef, FormSchema } from '@/types/form'
import { isDisplayField } from '@/types/form'
import type {
  ApprovalNode,
  AssigneeRule,
  AssigneeSource,
  AssigneeSourceType,
  Branch,
  CcNode,
  Comparison,
  ConditionNode,
  FillNode,
  ParallelNode,
  ReturnTarget,
  StepNode,
} from '@/types/flow'
import {
  ASSIGNEE_MODE_LABELS,
  ASSIGNEE_SOURCE_LABELS,
  COMPARISON_LABELS,

  isConditionGroup,
} from '@/types/flow'

const props = defineProps<{
  node: StepNode
  formSchema: FormSchema | null
  roleOptions: Array<{ value: number; label: string }>
  userOptions: Array<{ value: number; label: string }>
  returnTargets: ReturnTarget[]
  nodeNameById: Record<string, string>
}>()

const emit = defineEmits<{ change: [] }>()

const org = useOrgStore()
onMounted(() => void org.loadDeptTree())

function notify(): void {
  emit('change')
}

// --------------------------------------------------------------------------- 能力判断

const isApproval = computed(() => props.node.type === 'approval')
const isFill = computed(() => props.node.type === 'fill')
const isAssigneeNode = computed(() => isApproval.value || isFill.value)
const isCondition = computed(() => props.node.type === 'condition')
const isCc = computed(() => props.node.type === 'cc')
const isParallel = computed(() => props.node.type === 'parallel')

const assigneeNode = computed(() => props.node as ApprovalNode | FillNode)
const conditionNode = computed(() => props.node as ConditionNode)
const ccNode = computed(() => props.node as CcNode)

const modeOptions = (Object.keys(ASSIGNEE_MODE_LABELS) as Array<keyof typeof ASSIGNEE_MODE_LABELS>).map(
  (m) => ({ value: m, label: ASSIGNEE_MODE_LABELS[m] }),
)

const sourceTypeOptions = (
  Object.keys(ASSIGNEE_SOURCE_LABELS) as AssigneeSourceType[]
).map((t) => ({ value: t, label: ASSIGNEE_SOURCE_LABELS[t] }))

/** 表单里可作人员来源的字段 */
const userFieldOptions = computed(() =>
  fieldsOf(['user', 'user_multi']).map((f) => ({ value: f.key, label: `${f.label}（${f.key}）` })),
)

/** 表单里可作部门来源的字段 */
const deptFieldOptions = computed(() =>
  fieldsOf(['dept', 'dept_multi']).map((f) => ({ value: f.key, label: `${f.label}（${f.key}）` })),
)

/** 条件可引用的所有字段（含子表列） */
const allFieldOptions = computed(() => {
  const out: Array<{ value: string; label: string }> = []
  for (const section of props.formSchema?.sections ?? []) {
    for (const field of section.fields) {
      if (isDisplayField(field)) continue
      out.push({ value: field.key, label: `${field.label}（${field.key}）` })
      for (const col of field.columns ?? []) {
        out.push({
          value: `${field.key}[].${col.key}`,
          label: `${field.label} · ${col.label}`,
        })
      }
    }
  }
  return out
})

function fieldsOf(types: string[]): FieldDef[] {
  const out: FieldDef[] = []
  for (const section of props.formSchema?.sections ?? []) {
    for (const field of section.fields) {
      if (types.includes(field.type)) out.push(field)
    }
  }
  return out
}

// --------------------------------------------------------------------------- 审批人

function currentRule(): AssigneeRule {
  return isCc.value ? ccNode.value.cc_to : assigneeNode.value.assignee
}

/**
 * 发起人指定审批人的候选范围在**规则级** `initiator_select`，不在来源自身。
 * 后端 `AssigneeRule` 的校验要求：只要有 initiator_select 来源，规则级范围就必须存在。
 */
function ensureInitiatorScope(source?: AssigneeSource): AssigneeSource {
  const rule = currentRule()
  if (rule.initiator_select) return rule.initiator_select
  const scope: AssigneeSource = {
    type: 'role',
    scope_role_ids: source?.scope_role_ids ?? [],
    scope_dept_ids: source?.scope_dept_ids ?? [],
  }
  rule.initiator_select = scope
  return scope
}

function syncInitiatorScope(ids: number[]): void {
  const rule = currentRule()
  const scope = ensureInitiatorScope()
  scope.scope_role_ids = ids
  // 来源自身的 scope_* 字段保留并同步，兼容旧定义与只读查看
  for (const item of rule.sources) {
    if (item.type === 'initiator_select') item.scope_role_ids = ids
  }
  notify()
}

function addSource(rule: AssigneeRule): void {
  rule.sources.push({ type: 'role', role_ids: [] })
  notify()
}

function removeSource(rule: AssigneeRule, index: number): void {
  rule.sources.splice(index, 1)
  if (!rule.sources.some((s) => s.type === 'initiator_select')) {
    rule.initiator_select = null
  }
  notify()
}

function onSourceTypeChange(source: AssigneeSource, type: AssigneeSourceType): void {
  // 换来源类型时清掉旧类型的残留参数，避免把「选了角色」的输入留在 personnel 来源上
  source.user_ids = []
  source.role_ids = []
  source.field = null
  source.dept_ids = []
  source.dept_field = null
  source.node_id = null
  deptManagerModes.delete(source)
  source.type = type

  const rule = currentRule()
  if (type === 'initiator_select') {
    ensureInitiatorScope(source)
  } else if (!rule.sources.some((s) => s.type === 'initiator_select')) {
    // 已没有发起人指定来源，清掉候选范围，避免留下脏配置
    rule.initiator_select = null
  }
  notify()
}

/** 有「发起人指定」来源时需要配候选范围 */
const needsInitiatorScope = computed(() =>
  assigneeNode.value.assignee?.sources?.some((s) => s.type === 'initiator_select'),
)

// --------------------------------------------------------------------------- 部门主管

/** 部门主管的来源方式：发起人部门 / 固定部门 / 表单部门字段 */
type DeptManagerMode = 'initiator' | 'fixed' | 'field'

/**
 * 只用于界面状态：数据上「刚切到指定部门但还没选」与「用发起人部门」都是空的，
 * 只靠 dept_ids / dept_field 推导会让刚点的单选项立刻弹回去，看起来像点不动。
 * 用 WeakMap 按来源对象记住用户的选择；不参与保存。
 */
const deptManagerModes = reactive(new WeakMap<AssigneeSource, DeptManagerMode>())

function deptManagerMode(source: AssigneeSource): DeptManagerMode {
  const remembered = deptManagerModes.get(source)
  if (remembered === 'fixed' || remembered === 'field') return remembered
  if (source.dept_ids?.length) return 'fixed'
  if (source.dept_field) return 'field'
  return 'initiator'
}

function onDeptManagerModeChange(source: AssigneeSource, event: unknown): void {
  const mode = (event as { target: { value: DeptManagerMode } }).target.value
  deptManagerModes.set(source, mode)
  // 切换方式时清掉另一侧的配置，避免固定部门与表单字段同时生效产生歧义
  if (mode !== 'fixed') source.dept_ids = []
  if (mode !== 'field') source.dept_field = null
  notify()
}

// --------------------------------------------------------------------------- 退回

/** 退回目标的白名单。null 表示「允许全部前序」 */
const returnMode = computed<'all' | 'none' | 'some'>(() => {
  const configured = assigneeNode.value.return_targets
  if (configured === null || configured === undefined) return 'all'
  if (configured.length === 0) return 'none'
  return 'some'
})

function setReturnMode(mode: 'all' | 'none' | 'some'): void {
  const node = assigneeNode.value
  if (mode === 'all') node.return_targets = null
  else if (mode === 'none') node.return_targets = []
  else node.return_targets = props.returnTargets.map((t) => t.id)
  notify()
}

// --------------------------------------------------------------------------- 条件分支

function addBranch(): void {
  const node = conditionNode.value
  const index = node.branches.length + 1
  const branch: Branch = {
    id: `b${index}`,
    name: `分支 ${index}`,
    when: { op: 'and', conditions: [{ field: '', cmp: '==', value: '' }] },
    steps: [],
  }
  // 「否则」必须保持在最后
  const elseIndex = node.branches.findIndex((b) => b.when === null)
  if (elseIndex >= 0) node.branches.splice(elseIndex, 0, branch)
  else node.branches.push(branch)
  notify()
}

function addElseBranch(): void {
  const node = conditionNode.value
  if (node.branches.some((b) => b.when === null)) return
  node.branches.push({ id: 'else', name: '否则', when: null, steps: [] })
  notify()
}

function removeBranch(index: number): void {
  conditionNode.value.branches.splice(index, 1)
  notify()
}

function addCondition(branch: Branch): void {
  if (!branch.when) return
  branch.when.conditions.push({
    field: allFieldOptions.value[0]?.value ?? '',
    cmp: '==',
    value: '',
  })
  notify()
}

/** 按**引用**删除，避免过滤后的视图索引与原数组错位 */
function removeCondition(branch: Branch, cond: EditableCondition): void {
  const list = branch.when?.conditions
  if (!list) return
  const index = list.indexOf(cond as never)
  if (index >= 0) list.splice(index, 1)
  notify()
}

const comparisonOptions = (Object.keys(COMPARISON_LABELS) as Comparison[]).map((c) => ({
  value: c,
  label: COMPARISON_LABELS[c],
}))

/** 这些比较符不需要右值 */
function needsValue(cmp: Comparison): boolean {
  return cmp !== 'is_empty' && cmp !== 'is_not_empty'
}

/** 流程定义里所有可作为「上一节点」的候选 */
const stepOptions = computed(() => {
  const out: Array<{ value: string; label: string }> = []
  for (const [id, name] of Object.entries(props.nodeNameById)) {
    if (id !== props.node.id) out.push({ value: id, label: name })
  }
  return out
})

/** 供模板使用的类型断言辅助（Vue 模板里不能直接写 as 与行内对象类型） */
function asApproval(): ApprovalNode {
  return props.node as ApprovalNode
}
function asCondition(): ConditionNode {
  return props.node as ConditionNode
}

/** 并行组的聚合模式（可写计算属性，避免在模板里做类型断言） */
const parallelMode = computed({
  get: () => (props.node as ParallelNode).mode,
  set: (value: 'all' | 'any') => {
    ;(props.node as ParallelNode).mode = value
    notify()
  },
})

/** radio 的 change 事件取值（模板里写不了行内对象类型） */
function onReturnModeChange(event: unknown): void {
  const value = (event as { target: { value: 'all' | 'none' | 'some' } }).target.value
  setReturnMode(value)
}

/**
 * 条件行的可编辑视图。
 *
 * UI 只支持**扁平条件**（and/or 的嵌套组请在 JSON 里配）——
 * 图形化嵌套组编辑器排在后续里程碑。返回的是原对象引用，
 * 所以改它就是改定义；`removeCondition` 按引用删除，索引不会错位。
 */
interface EditableCondition {
  field: string
  cmp: Comparison
  value: string
}

function conditionsOf(branch: Branch): EditableCondition[] {
  const list = branch.when?.conditions ?? []
  return list.filter((c) => !isConditionGroup(c)) as EditableCondition[]
}
</script>

<template>
  <a-form layout="vertical" size="small" class="node-panel">
    <a-tabs>
      <!-- ------------------------------------------------ 基本 -->
      <a-tab-pane key="basic" tab="基本">
        <a-form-item label="节点名称" required>
          <a-input v-model:value="node.name" @change="notify" />
        </a-form-item>
        <a-form-item label="节点标识" help="流程定义内唯一；公式与退回目标会引用它">
          <a-input v-model:value="node.id" class="text-mono" @change="notify" />
        </a-form-item>

        <template v-if="isParallel">
          <a-form-item label="聚合模式">
            <a-select
              v-model:value="parallelMode"
              :options="[
                { value: 'all', label: '会签：全部成员通过才继续' },
                { value: 'any', label: '或签：任一成员通过即继续' },
              ]"
            />
          </a-form-item>
          <a-alert
            type="info"
            show-icon
            message="并行组的成员在左侧清单里单独配置"
            description="组内成员的通过规则各自设置；整组的汇合由这里的聚合模式决定。"
          />
        </template>

        <template v-if="isAssigneeNode">
          <a-form-item label="审批人模式">
            <a-select
              v-model:value="assigneeNode.assignee.mode"
              :options="modeOptions"
              @change="notify"
            />
          </a-form-item>
        </template>
      </a-tab-pane>

      <!-- ------------------------------------------------ 审批人 -->
      <a-tab-pane v-if="isAssigneeNode || isCc" key="assignee" tab="处理人">
        <a-alert
          type="info"
          show-icon
          class="mini-tip"
          message="多条来源的结果会合并去重；未匹配到任何人时转交平台管理员并标记异常"
        />

        <div
          v-for="(source, index) in (isCc ? ccNode.cc_to.sources : assigneeNode.assignee.sources)"
          :key="index"
          class="source-card"
        >
          <div class="source-head">
            <a-select
              :value="source.type"
              :options="sourceTypeOptions"
              size="small"
              class="source-type"
              @change="(v: AssigneeSourceType) => onSourceTypeChange(source, v)"
            />
            <span class="spacer" />
            <a-button
              type="text"
              size="small"
              danger
              @click="removeSource(isCc ? ccNode.cc_to : assigneeNode.assignee, index)"
            >
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>

          <!-- 指定人员 -->
          <a-select
            v-if="source.type === 'user'"
            v-model:value="source.user_ids"
            :options="userOptions"
            mode="multiple"
            placeholder="选择人员"
            class="source-value"
            show-search
            option-filter-prop="label"
            @change="notify"
          />

          <!-- 指定角色 -->
          <a-select
            v-else-if="source.type === 'role'"
            v-model:value="source.role_ids"
            :options="roleOptions"
            mode="multiple"
            placeholder="选择角色"
            class="source-value"
            show-search
            option-filter-prop="label"
            @change="notify"
          />

          <!-- 表单人员字段 -->
          <a-select
            v-else-if="source.type === 'form_user_field'"
            v-model:value="source.field"
            :options="userFieldOptions"
            placeholder="选择人员控件"
            class="source-value"
            show-search
            option-filter-prop="label"
            @change="notify"
          />

          <!-- 表单部门字段的负责人 -->
          <a-select
            v-else-if="source.type === 'form_dept_field'"
            v-model:value="source.field"
            :options="deptFieldOptions"
            placeholder="选择部门控件"
            class="source-value"
            show-search
            option-filter-prop="label"
            @change="notify"
          />

          <!-- 部门主管 -->
          <div v-else-if="source.type === 'dept_manager'">
            <a-radio-group
              :value="deptManagerMode(source)"
              size="small"
              @change="(e: unknown) => onDeptManagerModeChange(source, e)"
            >
              <a-radio value="initiator">发起人所在部门</a-radio>
              <a-radio value="fixed">指定部门</a-radio>
              <a-radio value="field">表单部门字段</a-radio>
            </a-radio-group>

            <a-tree-select
              v-if="deptManagerMode(source) === 'fixed'"
              :value="source.dept_ids ?? []"
              :tree-data="org.deptTree"
              :field-names="{ children: 'children', label: 'name', value: 'id' }"
              multiple
              tree-checkable
              tree-default-expand-all
              placeholder="选择部门（可多选），取其主管"
              class="source-value dept-select"
              allow-clear
              @change="(value: number[] | undefined) => { source.dept_ids = value ?? []; notify() }"
            />

            <a-select
              v-else-if="deptManagerMode(source) === 'field'"
              v-model:value="source.dept_field"
              :options="deptFieldOptions"
              placeholder="选择部门控件"
              class="source-value dept-select"
              allow-clear
              show-search
              option-filter-prop="label"
              @change="notify"
            />

            <div class="text-muted tiny">
              <template v-if="deptManagerMode(source) === 'initiator'">
                取发起人所在部门的负责人；本级没设主管时沿部门树向上找
              </template>
              <template v-else-if="deptManagerMode(source) === 'fixed'">
                取所选部门的负责人；本级没设主管时沿部门树向上找
              </template>
              <template v-else>
                取表单里填写的部门值的负责人
              </template>
            </div>
          </div>

          <!-- 上一节点处理人 -->
          <div v-else-if="source.type === 'prev_node_actors'">
            <a-select
              v-model:value="source.node_id"
              :options="stepOptions"
              placeholder="不选则取上一个完成的节点（首个节点为发起人）"
              class="source-value"
              allow-clear
              @change="notify"
            />
            <div class="text-muted tiny">选择「发起人」时，首个审批节点由提交申请的人处理</div>
          </div>

          <!-- 发起人指定 -->
          <div v-else-if="source.type === 'initiator_select'">
            <a-select
              :value="currentRule().initiator_select?.scope_role_ids ?? []"
              :options="roleOptions"
              mode="multiple"
              placeholder="候选人范围：角色（可多选）"
              class="source-value scope-select"
              @change="syncInitiatorScope"
            />
            <div class="text-muted tiny">发起人提交时从这些角色里挑人；还可叠加部门范围</div>
          </div>
        </div>

        <a-button type="dashed" block size="small" @click="addSource(isCc ? ccNode.cc_to : assigneeNode.assignee)">
          <template #icon><PlusOutlined /></template>
          添加来源
        </a-button>

        <a-form-item v-if="needsInitiatorScope && isAssigneeNode" label="未选择时的行为" class="mt">
          <a-select
            v-model:value="assigneeNode.assignee.on_empty"
            :options="[
              { value: 'to_admin', label: '转交平台管理员并标记异常' },
              { value: 'block_publish', label: '发布时校验并阻断' },
            ]"
            @change="notify"
          />
        </a-form-item>
      </a-tab-pane>

      <!-- ------------------------------------------------ 动作与退回 -->
      <a-tab-pane v-if="isAssigneeNode" key="actions" tab="动作">
        <template v-if="isApproval">
          <a-form-item label="驳回策略">
            <a-select
              v-model:value="asApproval().reject_policy"
              :options="[
                { value: 'reject_to_initiator', label: '允许驳回到发起人' },
                { value: 'reject_forbidden', label: '禁止驳回（只能退回或同意）' },
              ]"
              @change="notify"
            />
          </a-form-item>
          <a-form-item label="审批意见必填">
            <a-switch v-model:checked="asApproval().opinion_required" @change="notify" />
          </a-form-item>
          <a-form-item label="附件必填">
            <a-switch v-model:checked="asApproval().attachment_required" @change="notify" />
          </a-form-item>
        </template>

        <a-form-item label="可退回的目标">
          <a-radio-group
            :value="returnMode"
            button-style="solid"
            size="small"
            @change="onReturnModeChange"
          >
            <a-radio-button value="all">全部前序节点</a-radio-button>
            <a-radio-button value="none">禁止退回</a-radio-button>
            <a-radio-button value="some">自定义</a-radio-button>
          </a-radio-group>
        </a-form-item>

        <a-form-item v-if="returnMode === 'some'" label="允许退回给">
          <a-select
            v-model:value="assigneeNode.return_targets"
            :options="returnTargets.map((t) => ({ value: t.id, label: t.name }))"
            mode="multiple"
            placeholder="选择前序节点"
            @change="notify"
          />
          <template #extra>
            <span class="text-muted tiny">
              候选集由服务端按流程结构算出，只列出该节点之前可退回的审批/填写节点
            </span>
          </template>
        </a-form-item>
        <a-alert
          v-else-if="returnMode === 'all'"
          type="info"
          show-icon
          class="mini-tip"
          :message="`可退回 ${returnTargets.length} 个前序节点：${returnTargets.map((t) => t.name).join('、') || '（无）'}`"
        />
      </a-tab-pane>

      <!-- ------------------------------------------------ 字段权限 -->
      <a-tab-pane v-if="isAssigneeNode" key="permission" tab="字段权限">
        <FieldPermissionPanel
          :rule="assigneeNode.fields_permission"
          :form-schema="formSchema"
          @change="notify"
        />
      </a-tab-pane>

      <!-- ------------------------------------------------ 条件分支 -->
      <a-tab-pane v-if="isCondition" key="branches" tab="分支">
        <div v-for="(branch, index) in asCondition().branches" :key="branch.id" class="branch-card">
          <div class="branch-head">
            <a-input
              v-model:value="branch.name"
              size="small"
              placeholder="分支名称"
              class="branch-name"
              @change="notify"
            />
            <a-tag v-if="branch.when === null" color="default">否则</a-tag>
            <span class="spacer" />
            <a-button type="text" size="small" danger @click="removeBranch(index)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>

          <template v-if="branch.when">
            <div v-for="(cond, ci) in conditionsOf(branch)" :key="ci" class="cond-row">
              <a-select
                v-model:value="cond.field"
                :options="allFieldOptions"
                size="small"
                placeholder="字段"
                show-search
                option-filter-prop="label"
                class="cond-field"
                @change="notify"
              />
              <a-select
                v-model:value="cond.cmp"
                :options="comparisonOptions"
                size="small"
                class="cond-cmp"
                @change="notify"
              />
              <a-input
                v-if="needsValue(cond.cmp)"
                v-model:value="cond.value"
                size="small"
                placeholder="值"
                class="cond-value"
                @change="notify"
              />
              <a-button type="text" size="small" danger @click="removeCondition(branch, cond)">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
            <a-button type="dashed" block size="small" @click="addCondition(branch)">
              <template #icon><PlusOutlined /></template>
              添加条件
            </a-button>
            <div class="text-muted tiny mt-sm">
              分支内的节点在左侧清单里配置；分支走完会自动汇合回主线
            </div>
          </template>
        </div>

        <a-button type="dashed" block size="small" @click="addBranch">
          <template #icon><PlusOutlined /></template>
          添加分支
        </a-button>
        <a-button
          v-if="!asCondition().branches.some((b) => b.when === null)"
          type="link"
          size="small"
          block
          @click="addElseBranch"
        >
          添加「否则」分支
        </a-button>
        <a-alert
          v-else
          type="success"
          show-icon
          class="mini-tip mt"
          message="已配置「否则」分支：所有条件都不满足时走它"
        />
      </a-tab-pane>
    </a-tabs>
  </a-form>
</template>

<style scoped lang="scss">
.node-panel :deep(.ant-tabs-nav) {
  margin-bottom: 12px;
}

.mini-tip {
  margin-bottom: 12px;

  :deep(.ant-alert-message) {
    font-size: 12px;
  }
}

.source-card {
  padding: 8px;
  margin-bottom: 8px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}

/* 来源控件在窄属性面板里必须有显式宽度，否则多选下拉会塌成 0 宽，
   连 placeholder 与下拉菜单都看不到。 */
.source-value {
  width: 100%;
}

/* 部门主管的二级选择器与上面的方式单选留出间距 */
.dept-select {
  margin-top: 8px;
}

.source-head {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
}

.source-type {
  width: 150px;
}

.spacer {
  flex: 1;
}

.scope-select {
  margin-bottom: 4px;
}

.tiny {
  font-size: 11px;
}

.mt {
  margin-top: 12px;
}

.mt-sm {
  margin-top: 6px;
}

.branch-card {
  padding: 8px;
  margin-bottom: 10px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}

.branch-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.branch-name {
  width: 160px;
}

.cond-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.cond-field {
  flex: 1 1 auto;
  min-width: 0;
}

.cond-cmp {
  flex: 0 0 100px;
}

.cond-value {
  flex: 0 0 110px;
}
</style>

<script setup lang="ts">
import { Empty } from 'ant-design-vue'
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  TeamOutlined,
} from '@ant-design/icons-vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { ApiError } from '@/api/http'
import { deptApi } from '@/api/modules/dept'
import UserSelect from '@/components/common/UserSelect.vue'
import { useOrgStore } from '@/stores/org'
import type { DeptMember, DeptNode } from '@/types/org'
import { feedback } from '@/utils/feedback'


const org = useOrgStore()

const selectedId = ref<number | null>(null)
const selected = ref<DeptNode | null>(null)
const searchKeyword = ref('')

// --------------------------------------------------------------------------- 树

const expandedKeys = ref<string[]>([])

/** a-tree 的节点结构：key/title/children 供组件用，raw 保留后端原始数据供业务用。 */
interface DeptTreeNode {
  key: number
  title: string
  raw: DeptNode
  children: DeptTreeNode[]
}

const treeData = computed<DeptTreeNode[]>(() =>
  org.deptTree.map(function map(node): DeptTreeNode {
    return {
      key: node.id,
      title: node.name,
      raw: node,
      children: node.children.map(map),
    }
  }),
)

const filteredTree = computed<DeptTreeNode[]>(() => {
  const keyword = searchKeyword.value.trim()
  if (!keyword) return treeData.value

  function filter(nodes: DeptTreeNode[]): DeptTreeNode[] {
    const out: DeptTreeNode[] = []
    for (const node of nodes) {
      const children = filter(node.children)
      if (node.raw.name.includes(keyword) || node.raw.code.includes(keyword) || children.length) {
        out.push({ ...node, children })
      }
    }
    return out
  }
  return filter(treeData.value)
})

// 搜索时自动展开，否则命中的子节点藏在折叠里看不见
watch(searchKeyword, (keyword) => {
  if (!keyword) return
  const keys: string[] = []
  const walk = (nodes: DeptNode[]): void => {
    for (const node of nodes) {
      keys.push(String(node.id))
      walk(node.children)
    }
  }
  walk(org.deptTree)
  expandedKeys.value = keys
})

function onSelect(keys: (string | number)[]): void {
  const key = keys[0]
  selectedId.value = key === undefined ? null : Number(key)
}

/** 在树里按 id 找节点（含子节点）。 */
function findNode(nodes: DeptNode[], id: number): DeptNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const hit = findNode(node.children, id)
    if (hit) return hit
  }
  return null
}

watch([selectedId, () => org.deptTree], () => {
  if (selectedId.value === null) {
    selected.value = null
    return
  }
  const node = findNode(org.deptTree, selectedId.value)
  selected.value = node
  if (node) loadFormFrom(node)
})

// --------------------------------------------------------------------------- 表单

const form = reactive({
  name: '',
  code: '',
  parent_id: null as number | null,
  manager_user_id: null as number | null,
  sort_order: 0,
  status: 'ACTIVE',
})
const formErrors = reactive<Record<string, string>>({})
const saving = ref(false)

/** 供 UserSelect 显示已有主管姓名（搜索结果里可能没有这个人）。 */
const managerSeed = computed(() => {
  if (!selected.value?.manager_user_id || !selected.value.manager_name) return []
  return [
    {
      id: selected.value.manager_user_id,
      username: '',
      real_name: selected.value.manager_name,
      dept_id: selected.value.id,
      dept_name: null,
    },
  ]
})

function loadFormFrom(node: DeptNode): void {
  Object.assign(form, {
    name: node.name,
    code: node.code,
    parent_id: node.parent_id,
    manager_user_id: node.manager_user_id,
    sort_order: node.sort_order,
    status: node.status,
  })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
}

/** 父部门候选：排除自己与自己的子树（后端也会拦，这里先挡掉避免无谓报错）。 */
const parentOptions = computed(() => {
  const excluded = new Set<number>()
  if (selected.value) {
    const walk = (nodes: DeptNode[]): void => {
      for (const node of nodes) {
        if (node.id === selected.value!.id || excluded.has(node.parent_id ?? -1)) {
          excluded.add(node.id)
        }
        walk(node.children)
      }
    }
    walk(org.deptTree)
  }

  const out: Array<Record<string, unknown>> = []
  const build = (nodes: DeptNode[]): Record<string, unknown>[] =>
    nodes
      .filter((n) => !excluded.has(n.id))
      .map((n) => ({
        value: n.id,
        title: n.name,
        children: build(n.children),
      }))
  out.push(...build(org.deptTree))
  return out
})

async function save(): Promise<void> {
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
  if (!form.name) formErrors.name = '请输入部门名称'

  if (!selected.value) {
    if (!form.code) formErrors.code = '请输入部门编码'
    else if (!/^[A-Za-z0-9_.-]+$/.test(form.code)) {
      formErrors.code = '仅允许字母、数字、下划线、点、短横线'
    }
  }
  if (formErrors.name || formErrors.code) return

  saving.value = true
  try {
    if (selected.value) {
      await deptApi.update(selected.value.id, {
        name: form.name,
        parent_id: form.parent_id,
        manager_user_id: form.manager_user_id,
        sort_order: form.sort_order,
        status: form.status,
      })
      feedback.success('部门已更新')
    } else {
      const created = await deptApi.create({
        name: form.name,
        code: form.code,
        parent_id: form.parent_id,
        manager_user_id: form.manager_user_id,
        sort_order: form.sort_order,
        status: form.status,
      })
      feedback.success('部门已创建')
      selectedId.value = created.id
    }
    await org.loadDeptTree(true)
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.code === 'DEPT_CODE_EXISTS') formErrors.code = error.message
      else if (error.code === 'DEPT_PARENT_CYCLE' || error.code === 'DEPT_PARENT_SELF') {
        formErrors.parent_id = error.message
      } else if (error.code === 'MANAGER_NOT_FOUND' || error.code === 'MANAGER_DISABLED') {
        formErrors.manager_user_id = error.message
      }
    }
  } finally {
    saving.value = false
  }
}

/** 把右侧面板切到「新建」态；parentId 为 null 即建顶级部门。 */
function openCreatePanel(parentId: number | null): void {
  selectedId.value = null
  selected.value = null
  Object.assign(form, {
    name: '',
    code: '',
    parent_id: parentId,
    manager_user_id: null,
    sort_order: 0,
    status: 'ACTIVE',
  })
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
}

function startCreateRoot(): void {
  openCreatePanel(null)
}

function startCreateChild(): void {
  if (!selected.value) return
  // 先取到父级 id 再清空选择（清空后 selected 就没了）
  openCreatePanel(selected.value.id)
}

async function removeDept(): Promise<void> {
  if (!selected.value) return
  const ok = await feedback.confirm({
    title: `确定删除部门「${selected.value.name}」吗？`,
    content: '只有没有子部门、且没有成员的部门才能删除。',
    danger: true,
  })
  if (!ok) return
  try {
    await deptApi.remove(selected.value.id)
    feedback.success('部门已删除')
    selectedId.value = null
    selected.value = null
    await org.loadDeptTree(true)
  } catch {
    // 拦截器已提示（DEPT_HAS_CHILDREN / DEPT_HAS_MEMBERS）
  }
}

// --------------------------------------------------------------------------- 成员

const members = ref<DeptMember[]>([])
const membersLoading = ref(false)
const memberModalOpen = ref(false)
const memberSaving = ref(false)
const memberIds = ref<number[]>([])
const memberSeed = ref<Array<{ id: number; username: string; real_name: string }>>([])

const memberColumns = [
  { title: '用户名', dataIndex: 'username', key: 'username', width: 160 },
  { title: '姓名', dataIndex: 'real_name', key: 'real_name', width: 140 },
  { title: '职位', dataIndex: 'position', key: 'position' },
  { title: '状态', key: 'status', width: 90 },
]

async function loadMembers(): Promise<void> {
  if (!selected.value) {
    members.value = []
    return
  }
  membersLoading.value = true
  try {
    members.value = await deptApi.members(selected.value.id)
  } finally {
    membersLoading.value = false
  }
}

watch(selected, () => void loadMembers())

function openMemberModal(): void {
  memberIds.value = members.value.map((m) => m.id)
  memberSeed.value = members.value.map((m) => ({
    id: m.id,
    username: m.username,
    real_name: m.real_name,
  }))
  memberModalOpen.value = true
}

async function submitMembers(): Promise<void> {
  if (!selected.value) return
  memberSaving.value = true
  try {
    await deptApi.setMembers(selected.value.id, memberIds.value)
    memberModalOpen.value = false
    feedback.success('成员已更新')
    await Promise.all([loadMembers(), org.loadDeptTree(true)])
  } finally {
    memberSaving.value = false
  }
}

onMounted(async () => {
  await org.loadDeptTree()
  if (org.deptTree.length) {
    expandedKeys.value = org.deptTree.map((n) => String(n.id))
  }
})
</script>

<template>
  <div class="page-container">
    <a-row :gutter="16">
      <a-col :xs="24" :lg="8">
        <a-card :bordered="false" class="tree-card">
          <template #title>
            <a-space>
              <span>组织架构</span>
              <a-tag>{{ org.deptTree.length ? '已加载' : '空' }}</a-tag>
            </a-space>
          </template>
          <template #extra>
            <a-button size="small" @click="org.loadDeptTree(true)">
              <template #icon><ReloadOutlined /></template>
            </a-button>
          </template>

          <a-input-search             v-model:value="searchKeyword"
            placeholder="搜索部门名称或编码"
            allow-clear
            style="margin-bottom: 12px"
          />

          <a-tree             v-if="treeData.length"
            :tree-data="filteredTree"
            :selected-keys="selectedId === null ? [] : [selectedId]"
            v-model:expanded-keys="expandedKeys"
            block-node
            @select="onSelect"
          >
            <template #title="node">
              <span class="tree-title">
                <span>{{ (node.raw as DeptNode).name }}</span>
                <span v-if="(node.raw as DeptNode).member_count" class="member-count">
                  {{ (node.raw as DeptNode).member_count }}
                </span>
              </span>
            </template>
          </a-tree>
          <a-empty v-else description="还没有部门" :image="Empty.PRESENTED_IMAGE_SIMPLE" />

          <a-button type="dashed" block style="margin-top: 12px" @click="startCreateRoot">
            <template #icon><PlusOutlined /></template>
            新建部门
          </a-button>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="16">
        <a-card :bordered="false">
          <template #title>
            {{ selected ? `编辑：${selected.name}` : '新建部门' }}
          </template>
          <template #extra>
            <a-space v-if="selected">
              <a-button size="small" @click="startCreateChild">
                <template #icon><PlusOutlined /></template>
                添加子部门
              </a-button>
              <a-button size="small" danger @click="removeDept">
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </a-space>
          </template>

          <a-form layout="vertical" style="max-width: 560px">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item
                  label="部门名称"
                  required
                  :validate-status="formErrors.name ? 'error' : undefined"
                  :help="formErrors.name"
                >
                  <a-input v-model:value="form.name" placeholder="如：技术部" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item
                  label="部门编码"
                  :required="!selected"
                  :validate-status="formErrors.code ? 'error' : undefined"
                  :help="formErrors.code || (selected ? '编码创建后不可修改' : undefined)"
                >
                  <a-input                     v-model:value="form.code"
                    :disabled="!!selected"
                    placeholder="如：TECH"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item
              label="上级部门"
              :validate-status="formErrors.parent_id ? 'error' : undefined"
              :help="formErrors.parent_id"
            >
              <a-tree-select
                v-model:value="form.parent_id"
                :tree-data="parentOptions"
                placeholder="不选则为顶级部门"
                allow-clear
                tree-default-expand-all
                style="width: 100%"
              />
            </a-form-item>

            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item
                  label="部门主管"
                  :validate-status="formErrors.manager_user_id ? 'error' : undefined"
                  :help="
                    formErrors.manager_user_id ||
                    '用于「部门主管」类审批人的解析（PRD §3.3.2）'
                  "
                >
                  <UserSelect
                    v-model="form.manager_user_id"
                    :seed="managerSeed"
                    placeholder="选择主管"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="排序">
                  <a-input-number v-model:value="form.sort_order" :min="0" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="状态">
                  <a-select
                    v-model:value="form.status"
                    :options="[
                      { value: 'ACTIVE', label: '启用' },
                      { value: 'DISABLED', label: '停用' },
                    ]"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item v-if="selected && selected.manager_name" label="当前主管">
              <a-tag color="blue">{{ selected.manager_name }}</a-tag>
            </a-form-item>

            <a-space>
              <a-button type="primary" :loading="saving" @click="save">
                {{ selected ? '保存修改' : '创建部门' }}
              </a-button>
              <a-button @click="selected ? loadFormFrom(selected) : startCreateRoot()">重置</a-button>
            </a-space>
          </a-form>
        </a-card>

        <a-card v-if="selected" :bordered="false" style="margin-top: 16px">
          <template #title>
            <a-space>
              <TeamOutlined />
              <span>直属成员（{{ members.length }}）</span>
            </a-space>
          </template>
          <template #extra>
            <a-button size="small" type="primary" @click="openMemberModal">调整成员</a-button>
          </template>

          <a-table             :columns="memberColumns"
            :data-source="members"
            :loading="membersLoading"
            row-key="id"
            size="small"
            :pagination="false"
            :locale="{ emptyText: '该部门暂无直属成员' }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'position'">
                {{ record.position || '—' }}
              </template>
              <template v-else-if="column.key === 'status'">
                <a-tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">
                  {{ record.status === 'ACTIVE' ? '启用' : '停用' }}
                </a-tag>
              </template>
            </template>
          </a-table>
        </a-card>
      </a-col>
    </a-row>

    <a-modal
      v-model:open="memberModalOpen"
      :title="`调整「${selected?.name ?? ''}」的成员`"
      :confirm-loading="memberSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitMembers"
    >
      <a-alert
        type="info"
        show-icon
        message="覆盖式保存：不在列表中的原成员会被移出本部门。"
        style="margin-bottom: 16px"
      />
      <UserSelect v-model="memberIds" multiple :seed="memberSeed" placeholder="搜索并选择成员" />
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.tree-card {
  min-height: 420px;
}

.tree-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.member-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #e6f4ff;
  color: #1677ff;
  font-size: 11px;
  line-height: 1;
}
</style>

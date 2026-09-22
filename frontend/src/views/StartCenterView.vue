<script setup lang="ts">
/**
 * 发起中心（F3.1）。
 *
 * 只列出**我有权发起**的流程（服务端按 initiator_scope 过滤），
 * 外加我的草稿箱 —— 草稿是「填了一半」的入口，不该藏起来。
 */
import { ClockCircleOutlined, DeleteOutlined, RocketOutlined } from '@ant-design/icons-vue'
import { Button, Card, Empty, Space, Tag } from 'ant-design-vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { instanceApi } from '@/api/modules/instance'
import type { FlowTemplate } from '@/types/flow'
import type { InstanceItem } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'
import { feedback } from '@/utils/feedback'

const router = useRouter()

const flows = ref<FlowTemplate[]>([])
const drafts = ref<InstanceItem[]>([])
const loading = ref(false)

const grouped = computed(() => {
  const map = new Map<string, FlowTemplate[]>()
  for (const flow of flows.value) {
    const key = flow.category || '未分类'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(flow)
  }
  return [...map.entries()]
})

async function load(): Promise<void> {
  loading.value = true
  try {
    ;[flows.value, drafts.value] = await Promise.all([
      instanceApi.availableFlows(),
      instanceApi.listDrafts(),
    ])
  } finally {
    loading.value = false
  }
}

onMounted(load)

function start(flow: FlowTemplate): void {
  void router.push({ name: 'start-form', params: { flowTemplateId: flow.id } })
}

function resume(draft: InstanceItem): void {
  void router.push({
    name: 'start-form',
    params: { flowTemplateId: draft.flow_template_id },
    query: { draftId: draft.id },
  })
}

async function removeDraft(draft: InstanceItem): Promise<void> {
  const ok = await feedback.confirm({
    title: `删除草稿「${draft.title}」？`,
    danger: true,
  })
  if (!ok) return
  await instanceApi.deleteDraft(draft.id)
  feedback.success('草稿已删除')
  await load()
}
</script>

<template>
  <div class="page-container">
    <a-spin :spinning="loading">
      <!-- ------------------------------------------------ 草稿箱 -->
      <Card v-if="drafts.length" :bordered="false" class="block">
        <template #title>
          <Space>
            <ClockCircleOutlined />
            <span>我的草稿</span>
            <Tag>{{ drafts.length }}</Tag>
          </Space>
        </template>
        <div class="draft-list">
          <div v-for="draft in drafts" :key="draft.id" class="draft-item">
            <div class="draft-main">
              <a @click="resume(draft)">{{ draft.title }}</a>
              <span class="text-muted tiny">
                {{ draft.flow_template_name }} · 创建于 {{ formatDateTime(draft.created_at) }}
              </span>
            </div>
            <Space :size="4">
              <Button type="link" size="small" @click="resume(draft)">继续填写</Button>
              <Button type="link" size="small" danger @click="removeDraft(draft)">
                <template #icon><DeleteOutlined /></template>
              </Button>
            </Space>
          </div>
        </div>
      </Card>

      <!-- ------------------------------------------------ 可发起流程 -->
      <Card :bordered="false" class="block">
        <template #title>
          <Space>
            <RocketOutlined />
            <span>发起新流程</span>
          </Space>
        </template>

        <Empty v-if="!flows.length" description="你当前没有可发起的流程，请联系管理员" />

        <div v-for="[category, items] in grouped" :key="category" class="category">
          <div class="category-title">{{ category }}</div>
          <div class="flow-grid">
            <div v-for="flow in items" :key="flow.id" class="flow-card" @click="start(flow)">
              <div class="flow-name">{{ flow.name }}</div>
              <div class="flow-desc text-muted">
                {{ flow.description || `共 ${flow.node_count} 个审批节点` }}
              </div>
              <div class="flow-foot">
                <Tag color="green">v{{ flow.current_version_no }}</Tag>
                <span class="text-muted tiny">表单 v{{ flow.locked_form_version_no }}</span>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </a-spin>
  </div>
</template>

<style scoped lang="scss">
.block {
  border-radius: 8px;
  margin-bottom: 12px;
}

.draft-list {
  display: flex;
  flex-direction: column;
}

.draft-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f5f5f5;

  &:last-child {
    border-bottom: none;
  }
}

.draft-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.tiny {
  font-size: 11px;
}

.category {
  margin-bottom: 18px;
}

.category-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.65);
  margin-bottom: 10px;
}

.flow-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}

.flow-card {
  padding: 14px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;

  &:hover {
    border-color: #91caff;
    box-shadow: 0 2px 10px rgb(22 119 255 / 10%);
    transform: translateY(-1px);
  }
}

.flow-name {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
}

.flow-desc {
  font-size: 12px;
  min-height: 34px;
  line-height: 17px;
}

.flow-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}
</style>

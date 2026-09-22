<script setup lang="ts">
import { Select } from 'ant-design-vue'
import { computed, onMounted, ref, watch } from 'vue'

import { useOrgStore } from '@/stores/org'
import type { UserOption } from '@/types/org'

/**
 * 人员选择器（单选 / 多选），远程搜索。
 *
 * 已选中但不在当前搜索结果里的人必须仍能正确显示名字，否则编辑一个主管在
 * 第 51 位之后的部门时会看到空标签。做法是把「外部已知的人」塞进缓存，
 * 选项列表 = 搜索结果 ∪ 已选缓存。
 */
const props = withDefaults(
  defineProps<{
    modelValue: number | number[] | null
    multiple?: boolean
    placeholder?: string
    disabled?: boolean
    /** 调用方已知的候选项（如部门主管的姓名），用于补齐未出现在搜索结果里的标签 */
    seed?: UserOption[]
  }>(),
  { multiple: false, placeholder: '请选择人员', disabled: false, seed: () => [] },
)

const emit = defineEmits<{ 'update:modelValue': [number | number[] | null] }>()

const org = useOrgStore()
const fetched = ref<UserOption[]>([])
const cache = ref(new Map<number, UserOption>())
const loading = ref(false)

const selectedIds = computed<number[]>(() => {
  if (props.modelValue === null || props.modelValue === undefined) return []
  return Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]
})

const options = computed(() => {
  const merged = new Map<number, UserOption>()
  for (const item of fetched.value) merged.set(item.id, item)
  // 已选中的优先用缓存里的信息，保证标签正确
  for (const id of selectedIds.value) {
    const hit = cache.value.get(id)
    if (hit) merged.set(id, hit)
  }
  return [...merged.values()].map((u) => ({
    value: u.id,
    label: u.dept_name ? `${u.real_name}（${u.dept_name}）` : u.real_name,
  }))
})

function remember(users: UserOption[]): void {
  const next = new Map(cache.value)
  for (const u of users) next.set(u.id, u)
  cache.value = next
}

watch(
  () => props.seed,
  (users) => remember(users),
  { immediate: true, deep: true },
)

async function search(keyword: string): Promise<void> {
  loading.value = true
  try {
    const users = await org.searchUsers({ keyword: keyword || undefined })
    fetched.value = users
    remember(users)
  } finally {
    loading.value = false
  }
}

onMounted(() => void search(''))

/** antd 的 change 回调给的是 SelectValue（清空时为 undefined），这里归一成 null。 */
function onChange(value: unknown): void {
  emit('update:modelValue', (value ?? null) as number | number[] | null)
}
</script>

<template>
  <Select
    :value="modelValue ?? undefined"
    :mode="multiple ? 'multiple' : undefined"
    :options="options"
    :placeholder="placeholder"
    :disabled="disabled"
    :loading="loading"
    :filter-option="false"
    allow-clear
    show-search
    option-filter-prop="label"
    style="width: 100%"
    @search="search"
    @change="onChange"
  />
</template>

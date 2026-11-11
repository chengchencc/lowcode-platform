<script setup lang="ts">
/**
 * 附件 / 图片控件（PRD §3.2.2 文件分组）。
 *
 * 值是一组 attachment id。上传后先落 TEMP，业务提交时由服务端绑定
 * （见 backend/app/services/file_service.py）。
 */
import { DeleteOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { Image, Upload } from 'ant-design-vue'
import { computed, onUnmounted, ref, watch } from 'vue'

import { fileApi } from '@/api/modules/form'
import type { AttachmentInfo, FieldDef } from '@/types/form'
import { downloadFile, fetchObjectUrl } from '@/utils/download'
import { feedback } from '@/utils/feedback'

const props = defineProps<{
  field: FieldDef
  modelValue: unknown
  editable: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [unknown] }>()

const AImage = Image
const AUpload = Upload

const uploading = ref(false)

const isImage = computed(() => props.field.type === 'image')

/** 已上传的附件元数据。控件自己缓存文件名，避免为了显示名字再拉一遍接口。 */
const meta = ref(new Map<number, AttachmentInfo>())

const ids = computed<number[]>(() => {
  const v = props.modelValue
  if (v === null || v === undefined || v === '') return []
  return (Array.isArray(v) ? v : [v]).map(Number).filter((n) => !Number.isNaN(n))
})

const items = computed(() =>
  ids.value.map((id) => ({
    id,
    info: meta.value.get(id),
    name: meta.value.get(id)?.file_name ?? `附件 #${id}`,
  })),
)

/**
 * 图片缩略图要的是能塞进 `<img src>` 的地址，而下载接口只认 Authorization 头 ——
 * 直接写接口地址会 401，必须先取回 blob 再转本地 URL。
 * 卸载时统一 revoke，避免 blob 常驻内存。
 */
const objectUrls = ref(new Map<number, string>())

async function ensureObjectUrl(id: number): Promise<void> {
  if (objectUrls.value.has(id)) return
  try {
    const url = await fetchObjectUrl(fileApi.downloadPath(id))
    const next = new Map(objectUrls.value)
    next.set(id, url)
    objectUrls.value = next
  } catch {
    // 没有权限 / 文件已删：留空占位即可，不打扰用户
  }
}

async function ensureMeta(id: number): Promise<void> {
  if (meta.value.has(id)) return
  try {
    remember(await fileApi.info(id))
  } catch {
    // 无权限/已删除：保留 `附件 #id` 占位，不打断页面
  }
}

watch(
  ids,
  (current) => {
    for (const id of current) {
      void ensureMeta(id)
      if (isImage.value) void ensureObjectUrl(id)
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  for (const url of objectUrls.value.values()) URL.revokeObjectURL(url)
})

async function open(item: { id: number; name: string }): Promise<void> {
  try {
    await downloadFile(fileApi.downloadPath(item.id), item.name)
  } catch {
    feedback.error('附件打不开（可能没有权限）')
  }
}

const maxCount = computed(() => props.field.validators?.max_file_count ?? undefined)
const reachLimit = computed(() => maxCount.value != null && ids.value.length >= maxCount.value)

function remember(info: AttachmentInfo): void {
  const next = new Map(meta.value)
  next.set(info.id, info)
  meta.value = next
}

/** 交给 Upload 的 beforeUpload：拦掉自动上传，改由我们手动调接口。 */
async function handleFile(file: File): Promise<boolean> {
  uploading.value = true
  try {
    const info = await fileApi.upload(file, isImage.value)
    remember(info)
    emit('update:modelValue', [...ids.value, info.id])
    feedback.success(`已上传「${info.file_name}」`)
  } catch {
    // 拦截器已提示（扩展名不在白名单 / 超过大小上限等）
  } finally {
    uploading.value = false
  }
  return false
}

function remove(id: number): void {
  emit(
    'update:modelValue',
    ids.value.filter((x) => x !== id),
  )
}
</script>

<template>
  <div class="attachment-control">
    <div v-if="items.length" class="attachment-list">
      <div v-for="item in items" :key="item.id" class="attachment-item">
        <template v-if="isImage">
          <AImage
            v-if="objectUrls.get(item.id)"
            :src="objectUrls.get(item.id)"
            :width="72"
            :height="72"
            class="thumb"
          />
          <div v-else class="thumb placeholder text-muted">加载中…</div>
        </template>
        <template v-else>
          <a class="file-name" @click="open(item)">{{ item.name }}</a>
        </template>

        <div class="attachment-actions">
          <a title="查看" @click="open(item)">
            <EyeOutlined />
          </a>
          <a v-if="editable" class="danger" title="移除" @click="remove(item.id)">
            <DeleteOutlined />
          </a>
        </div>
      </div>
    </div>

    <div v-if="!items.length && !editable" class="text-muted">—</div>

    <div v-if="editable" class="attachment-upload">
      <AUpload
        :before-upload="handleFile"
        :show-upload-list="false"
        :accept="isImage ? 'image/*' : undefined"
        :disabled="uploading || reachLimit"
      >
        <a-button :loading="uploading" :disabled="reachLimit">
          <template #icon><PlusOutlined /></template>
          {{ isImage ? '上传图片' : '上传附件' }}
        </a-button>
      </AUpload>
      <span v-if="maxCount" class="text-muted hint">
        {{ ids.length }} / {{ maxCount }}
      </span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.attachment-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}

.attachment-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}

.thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border: 1px dashed #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
}

.thumb :deep(img) {
  border-radius: 4px;
  object-fit: cover;
}

.file-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  font-size: 13px;

  .danger {
    color: #ff4d4f;
  }
}

.attachment-upload {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hint {
  font-size: 12px;
}
</style>

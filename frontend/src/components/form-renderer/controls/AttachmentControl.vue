<script setup lang="ts">
/**
 * 附件 / 图片控件（PRD §3.2.2 文件分组）。
 *
 * 值是一组 attachment id。上传后先落 TEMP，业务提交时由服务端绑定
 * （见 backend/app/services/file_service.py）。
 */
import { DeleteOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { Image, Upload } from 'ant-design-vue'
import { computed, ref } from 'vue'

import { fileApi } from '@/api/modules/form'
import type { AttachmentInfo, FieldDef } from '@/types/form'
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
    url: fileApi.downloadUrl(id),
  })),
)

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
          <AImage :src="item.url" :width="72" :height="72" class="thumb" />
        </template>
        <template v-else>
          <a :href="item.url" target="_blank" class="file-name">{{ item.name }}</a>
        </template>

        <div class="attachment-actions">
          <a :href="item.url" target="_blank" title="查看">
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

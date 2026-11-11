<script setup lang="ts">
/**
 * 展示型控件（M8）：标题 / 说明 / 分割线 / 图片 / 受限富文本。
 *
 * 不绑定实例数据，也不参与字段权限矩阵的编辑项；渲染器只负责按分区
 * 的可见性把它显示出来。富文本走 `utils/richText.ts` 的白名单渲染，
 * 不使用任意 HTML。
 */
import { computed } from 'vue'

import type { DisplayConfig, FieldDef } from '@/types/form'
import { renderRichText } from '@/utils/richText'

const props = defineProps<{ field: FieldDef }>()

const display = computed<DisplayConfig>(() => props.field.display ?? {})
const headingTag = computed(() => `h${display.value.level ?? 2}`)
const text = computed(() => display.value.text ?? '')
</script>

<template>
  <div class="display-block" :class="`display-${field.type}`">
    <component
      :is="headingTag"
      v-if="field.type === 'heading'"
      class="display-heading"
    >
      {{ text || field.label }}
    </component>

    <p v-else-if="field.type === 'paragraph'" class="display-paragraph">
      {{ text }}
    </p>

    <a-divider v-else-if="field.type === 'divider'" class="display-divider">
      {{ text }}
    </a-divider>

    <img
      v-else-if="field.type === 'image_view' && display.url"
      :src="display.url"
      :alt="display.alt || field.label"
      class="display-image"
      loading="lazy"
    />

    <div
      v-else-if="field.type === 'rich_text'"
      class="display-rich"
      v-html="renderRichText(display.markdown ?? '')"
    />

    <span v-else class="display-empty">未配置展示内容</span>
  </div>
</template>

<style scoped lang="scss">
.display-block {
  width: 100%;
  padding: 4px 0;
}

.display-heading {
  margin: 4px 0 8px;
  color: rgba(0, 0, 0, 0.88);
  font-weight: 600;
  line-height: 1.4;
}

h1.display-heading {
  font-size: 22px;
}

h2.display-heading {
  font-size: 18px;
}

h3.display-heading {
  font-size: 15px;
}

.display-paragraph {
  margin: 0 0 8px;
  color: rgba(0, 0, 0, 0.72);
  white-space: pre-wrap;
  line-height: 1.7;
}

.display-divider {
  margin: 8px 0;
  color: rgba(0, 0, 0, 0.55);
  font-size: 12px;
}

.display-image {
  display: block;
  max-width: 100%;
  max-height: 360px;
  border-radius: 6px;
  object-fit: contain;
}

.display-rich {
  color: rgba(0, 0, 0, 0.72);
  line-height: 1.7;

  :deep(p) {
    margin: 0 0 8px;
  }

  :deep(ul) {
    margin: 0 0 8px;
    padding-left: 20px;
  }

  :deep(code) {
    padding: 1px 4px;
    border-radius: 3px;
    background: #f5f5f5;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }

  :deep(a) {
    color: #1677ff;
  }

  :deep(h1),
  :deep(h2),
  :deep(h3) {
    margin: 4px 0 8px;
    font-weight: 600;
    line-height: 1.4;
  }
}

.display-empty {
  color: rgba(0, 0, 0, 0.35);
  font-size: 12px;
}
</style>

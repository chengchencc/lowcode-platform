<script setup lang="ts">
import { App } from 'ant-design-vue'

import { registerFeedback } from '@/utils/feedback'

/**
 * 必须作为 `<a-app>` 的子组件存在 —— `App.useApp()` 只能取到祖先 `<a-app>`
 * 提供的实例。这里把它注册到 utils/feedback，供 axios 拦截器等非组件代码使用。
 */
const { message, modal } = App.useApp()

registerFeedback({
  success: (content) => void message.success(content),
  error: (content) => void message.error(content),
  warning: (content) => void message.warning(content),
  info: (content) => void message.info(content),
  confirm: (options) =>
    new Promise<boolean>((resolve) => {
      modal.confirm({
        title: options.title,
        content: options.content,
        okText: options.okText ?? '确定',
        cancelText: options.cancelText ?? '取消',
        okButtonProps: options.danger ? { danger: true } : undefined,
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    }),
})
</script>

<template>
  <router-view />
</template>

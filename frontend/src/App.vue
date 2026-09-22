<script setup lang="ts">
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

import AppFrame from '@/AppFrame.vue'

dayjs.locale('zh-cn')

const theme = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 6,
  },
}
</script>

<template>
  <a-config-provider :locale="zhCN" :theme="theme">
    <!-- a-app 提供 message/modal 的上下文（中文 locale 与主题才会生效） -->
    <a-app>
      <AppFrame />
    </a-app>
  </a-config-provider>
</template>

<script setup lang="ts">

</script>

<template>
  <div class="not-found">
    <a-result status="404" title="404" sub-title="抱歉，你访问的页面不存在">
      <template #extra>
        <router-link to="/">
          <a-button type="primary">返回首页</a-button>
        </router-link>
      </template>
    </a-result>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>

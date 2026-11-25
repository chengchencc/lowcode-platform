<script setup lang="ts">
import { LockOutlined, UserOutlined } from '@ant-design/icons-vue'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { appInitial, appName } from '@/utils/appMeta'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const form = reactive({ username: '', password: '' })
const errors = reactive<Record<string, string>>({})
const submitting = ref(false)
const generalError = ref('')

async function handleSubmit(): Promise<void> {
  Object.keys(errors).forEach((k) => delete errors[k])
  generalError.value = ''

  if (!form.username) errors.username = '请输入用户名'
  if (!form.password) errors.password = '请输入密码'
  if (Object.keys(errors).length) return

  submitting.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = route.query.redirect
    await router.replace(typeof redirect === 'string' ? redirect : { name: 'dashboard' })
  } catch (error) {
    // 登录失败就地展示在表单里，不弹全局 toast
    generalError.value =
      error instanceof ApiError ? error.message : '登录失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <span class="brand-mark">{{ appInitial }}</span>
        <div>
          <h1 :title="appName">{{ appName }}</h1>
          <!-- <p>低代码表单 + 审批流平台</p> -->
        </div>
      </div>

      <a-alert
        v-if="generalError"
        type="error"
        show-icon
        :message="generalError"
        class="login-alert"
      />

      <a-form layout="vertical" @submit.prevent="handleSubmit">
        <a-form-item
          label="用户名"
          :validate-status="errors.username ? 'error' : undefined"
          :help="errors.username"
        >
          <a-input
            v-model:value="form.username"
            size="large"
            placeholder="请输入用户名"
            autocomplete="username"
            allow-clear
          >
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>

        <a-form-item
          label="密码"
          :validate-status="errors.password ? 'error' : undefined"
          :help="errors.password"
        >
          <a-input-password
            v-model:value="form.password"
            size="large"
            placeholder="请输入密码"
            autocomplete="current-password"
            @press-enter="handleSubmit"
          >
            <template #prefix><LockOutlined /></template>
          </a-input-password>
        </a-form-item>

        <a-button
          type="primary"
          size="large"
          block
          :loading="submitting"
          html-type="submit"
        >
          登录
        </a-button>
      </a-form>
    </div>
  </div>
</template>

<style scoped lang="scss">
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e8f0fe 0%, #f5f6f8 55%, #eef2f7 100%);
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: #fff;
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: 0 8px 32px rgb(15 34 67 / 10%);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;

  h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    line-height: 1.35;
    overflow-wrap: anywhere;
  }

  p {
    margin: 2px 0 0;
    font-size: 12px;
    color: rgba(0, 0, 0, 0.45);
  }
}

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: #1677ff;
  color: #fff;
  font-weight: 700;
  font-size: 17px;
}

.login-alert {
  margin-bottom: 16px;
}
</style>

<script setup lang="ts">
import type { MenuProps } from 'ant-design-vue'
import {
  KeyOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons-vue'
import { computed, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/modules/auth'
import { MENU_DEFAULT_PARAMS, buildMenuItems, navigableNames } from '@/layouts/menu'
import { taskApi } from '@/api/modules/instance'
import { ApiError } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type { TodoSummary } from '@/types/instance'
import { feedback } from '@/utils/feedback'

/** 待办角标轮询间隔（F7.2 要求 ≤10s 感知） */
const POLL_INTERVAL_MS = 10_000


const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const app = useAppStore()

// --------------------------------------------------------------------------- 待办角标

/**
 * 角标计数（F7.2「≤10s 感知新任务」）。
 *
 * V1 用轮询而不是 WebSocket —— 千人内部系统下每 10s 一次轻量查询完全够用，
 * 而 WebSocket 要处理重连、鉴权、多标签页，成本远高于收益。
 */
const summary = ref<TodoSummary>({ todo: 0, cc_unread: 0, mine_running: 0 })
let pollTimer: ReturnType<typeof setInterval> | null = null

async function refreshSummary(): Promise<void> {
  try {
    summary.value = await taskApi.summary()
  } catch {
    // 轮询失败静默 —— 网络抖动不该弹提示打断用户
  }
}

onMounted(() => {
  void refreshSummary()
  pollTimer = setInterval(() => void refreshSummary(), POLL_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

/** 处理完任务后立刻刷新角标，不等到下一次轮询 */
watch(
  () => route.fullPath,
  () => void refreshSummary(),
)

provide('refreshTodoSummary', refreshSummary)

const menuItems = computed<MenuProps['items']>(() =>
  buildMenuItems({
    isAdmin: auth.isAdmin,
    isDesigner: auth.isDesigner,
    todoCount: summary.value.todo,
    ccUnread: summary.value.cc_unread,
  }),
)

const selectedKeys = computed<string[]>(() => [String(route.name ?? 'dashboard')])

const openKeys = ref<string[]>(['org', 'design'])
const mobileMenuOpen = ref(false)

/**
 * 可跳转的菜单 key 从**路由表推导**（见 layouts/menu.ts 的说明）——
 * 手维护白名单已经漏过两次，表现都是「点了没反应」。
 */
const navigable = computed(() => navigableNames(router))

function onMenuClick(info: { key: string | number }): void {
  const key = String(info.key)
  mobileMenuOpen.value = false
  if (navigable.value.has(key)) {
    void router.push({ name: key, params: MENU_DEFAULT_PARAMS[key] })
    return
  }
  // 菜单项与路由对不上：开发期直接喊出来，别让它退化成「点了没反应」
  if (key.startsWith('org-') || key === 'design' || key === 'org') return
  if (import.meta.env.DEV) {
    console.warn(`[menu] 菜单项「${key}」没有对应的路由，点击不会有反应`)
  }
}

// --------------------------------------------------------------------------- 修改密码

const passwordOpen = ref(false)
const passwordSaving = ref(false)
const passwordForm = reactive({ old_password: '', new_password: '', confirm: '' })
const passwordErrors = reactive<Record<string, string>>({})

function openPasswordModal(): void {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm = ''
  Object.keys(passwordErrors).forEach((k) => delete passwordErrors[k])
  passwordOpen.value = true
}

async function submitPassword(): Promise<void> {
  Object.keys(passwordErrors).forEach((k) => delete passwordErrors[k])

  if (!passwordForm.old_password) passwordErrors.old_password = '请输入当前密码'
  if (passwordForm.new_password.length < 6) passwordErrors.new_password = '新密码至少 6 位'
  if (passwordForm.new_password !== passwordForm.confirm) {
    passwordErrors.confirm = '两次输入的新密码不一致'
  }
  if (Object.keys(passwordErrors).length) return

  passwordSaving.value = true
  try {
    await authApi.changePassword(passwordForm.old_password, passwordForm.new_password)
    passwordOpen.value = false
    // 后端改密会递增 token_version，当前会话立即失效，必须重新登录
    await auth.logout()
    feedback.success('密码已修改，请重新登录')
    router.push({ name: 'login' })
  } catch (error) {
    if (error instanceof ApiError && error.code === 'OLD_PASSWORD_MISMATCH') {
      passwordErrors.old_password = error.message
    }
    // 其他错误已由拦截器统一提示
  } finally {
    passwordSaving.value = false
  }
}

async function handleLogout(): Promise<void> {
  const ok = await feedback.confirm({ title: '确定要退出登录吗？' })
  if (!ok) return
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <a-layout class="app-layout">
    <a-layout-sider
      v-model:collapsed="app.sidebarCollapsed"
      class="app-sider"
      :trigger="null"
      collapsible
      theme="dark"
      :width="220"
    >
      <div class="logo">
        <span class="logo-mark">一</span>
        <span v-if="!app.sidebarCollapsed" class="logo-text">流程平台</span>
      </div>
      <a-menu         theme="dark"
        mode="inline"
        :items="menuItems"
        :selected-keys="selectedKeys"
        v-model:open-keys="openKeys"
        @click="onMenuClick"
      />
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="app-header">
        <MenuOutlined class="mobile-menu-btn" @click="mobileMenuOpen = true" />
        <component
          :is="app.sidebarCollapsed ? MenuUnfoldOutlined : MenuFoldOutlined"
          class="collapse-btn desktop-collapse-btn"
          @click="app.toggleSidebar"
        />
        <div class="header-right">
          <a-dropdown placement="bottomRight">
            <div class="user-chip">
              <a-avatar size="small" :style="{ backgroundColor: '#1677ff' }">
                {{ auth.displayName.slice(0, 1) }}
              </a-avatar>
              <span class="user-name">{{ auth.displayName }}</span>
             <!--  <span v-if="auth.user?.dept_name" class="user-dept">
                {{ auth.user.dept_name }}
              </span> -->
            </div>
            <template #overlay>
              <a-menu>
                <a-menu-item key="password" @click="openPasswordModal">
                  <KeyOutlined />
                  <span style="margin-left: 8px">修改密码</span>
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout" danger @click="handleLogout">
                  <LogoutOutlined />
                  <span style="margin-left: 8px">退出登录</span>
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="app-content">
        <router-view />
      </a-layout-content>
    </a-layout>

    <a-drawer
      v-model:open="mobileMenuOpen"
      placement="left"
      :width="220"
      :closable="false"
      class="mobile-menu-drawer"
      :body-style="{ padding: 0, background: '#001529' }"
    >
      <div class="logo">
        <span class="logo-mark">FF</span>
        <span class="logo-text">FlowForm</span>
      </div>
      <a-menu
        theme="dark"
        mode="inline"
        :items="menuItems"
        :selected-keys="selectedKeys"
        v-model:open-keys="openKeys"
        @click="onMenuClick"
      />
    </a-drawer>

    <a-modal
      v-model:open="passwordOpen"
      title="修改密码"
      :confirm-loading="passwordSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitPassword"
    >
      <a-alert
        type="info"
        show-icon
        message="修改成功后，所有已登录的会话都会失效，需要重新登录。"
        style="margin-bottom: 16px"
      />
      <a-form layout="vertical">
        <a-form-item
          label="当前密码"
          :validate-status="passwordErrors.old_password ? 'error' : undefined"
          :help="passwordErrors.old_password"
        >
          <a-input-password v-model:value="passwordForm.old_password" autocomplete="current-password" />
        </a-form-item>
        <a-form-item
          label="新密码"
          :validate-status="passwordErrors.new_password ? 'error' : undefined"
          :help="passwordErrors.new_password"
        >
          <a-input-password v-model:value="passwordForm.new_password" autocomplete="new-password" />
        </a-form-item>
        <a-form-item
          label="确认新密码"
          :validate-status="passwordErrors.confirm ? 'error' : undefined"
          :help="passwordErrors.confirm"
        >
          <a-input-password
            v-model:value="passwordForm.confirm"
            autocomplete="new-password"
            @press-enter="submitPassword"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<style scoped lang="scss">
.app-layout {
  min-height: 100vh;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  color: #fff;
  overflow: hidden;
  white-space: nowrap;
}

.logo-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  border-radius: 6px;
  background: #1677ff;
  font-weight: 700;
  font-size: 13px;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px 0 16px;
  background: #fff;
  box-shadow: 0 1px 4px rgb(0 0 0 / 6%);
}

.collapse-btn,
.mobile-menu-btn {
  font-size: 17px;
  cursor: pointer;
  color: rgba(0, 0, 0, 0.65);

  &:hover {
    color: #1677ff;
  }
}

.mobile-menu-btn {
  display: none;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;

  &:hover {
    background: rgba(0, 0, 0, 0.03);
  }
}

.user-name {
  font-size: 14px;
}

.user-dept {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.app-content {
  margin: 0;
  overflow: auto;
}

@media (max-width: 768px) {
  .app-sider {
    display: none;
  }

  .desktop-collapse-btn {
    display: none;
  }

  .mobile-menu-btn {
    display: inline-flex;
  }

  .app-header {
    padding: 0 12px;
  }

  .user-name,
  .user-dept {
    display: none;
  }

  .app-content {
    overflow-x: hidden;
  }
}
</style>

<style lang="scss">
/* a-menu 的 label 是渲染函数产出的节点，作用域样式选不中，放全局 */
.menu-soon {
  display: inline-flex;
  align-items: center;
  gap: 6px;

  em {
    font-style: normal;
    font-size: 10px;
    line-height: 16px;
    padding: 0 5px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.18);
    color: rgba(255, 255, 255, 0.65);
  }
}

.menu-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
  width: 100%;
}

/* 待办/未读角标（F7.2） */
.menu-badge {
  font-style: normal;
  font-size: 11px;
  line-height: 16px;
  min-width: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #ff4d4f;
  color: #fff;
  text-align: center;
}
</style>

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import 'ant-design-vue/dist/reset.css'
import '@/styles/index.scss'

import App from '@/App.vue'
import { setupDirectives } from '@/directives/permission'
import router from '@/router'
import { setupGuards } from '@/router/guards'

const app = createApp(App)

// pinia 必须在注册路由守卫之前安装：守卫里会 useAuthStore()
app.use(createPinia())
setupGuards(router)
app.use(router)
setupDirectives(app)

app.mount('#app')

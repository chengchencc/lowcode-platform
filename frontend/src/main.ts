import Antd from 'ant-design-vue'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import 'ant-design-vue/dist/reset.css'
import '@/styles/index.scss'

import App from '@/App.vue'
import { setupDirectives } from '@/directives/permission'
import router from '@/router'
import { setupGuards } from '@/router/guards'

const app = createApp(App)

// Ant Design Vue 全量全局注册。
//
// 为什么不按需/逐文件 import：模板里写成 <a-button> 这类 kebab 标签时，
// 未注册的组件**不会报错** —— vue-tsc 把它当成未知自定义元素放行，vite build
// 也照常通过，只在浏览器里静默渲染成空元素。M1 就这么漏掉过大半个界面。
// 全局注册让所有 a-* 标签在任意 .vue 里可用，从此不存在这种失败模式。
//
// 代价是打包体积（不做 tree-shaking）。面向单组织 ≤1000 人的内部系统，
// 这点体积换掉一整类静默 bug 是划算的。
app.use(Antd)

// pinia 必须在注册路由守卫之前安装：守卫里会 useAuthStore()
app.use(createPinia())
setupGuards(router)
app.use(router)
setupDirectives(app)

app.mount('#app')

/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 前端一律请求 /api/v1/...，由这里转发到后端，避免开发期跨域与硬编码域名
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // antd 全量注册后体积可观（约 1.6MB / gzip 500KB）。拆成独立 vendor chunk：
        // 业务代码改动时用户不必重新下载这部分，能显著改善回访加载。
        manualChunks: {
          antd: ['ant-design-vue', '@ant-design/icons-vue'],
          vue: ['vue', 'vue-router', 'pinia'],
        },
      },
    },
    // antd vendor chunk 约 1.44MB（gzip 438KB），是「全量注册」这个决策的已知代价
    // （见 docs/TECH-DESIGN.md §6.3）。阈值设在它之上，避免每次构建都刷警告。
    chunkSizeWarningLimit: 1600,
  },
  test: {
    // 用 happy-dom 而非 jsdom：jsdom 30 的依赖链（html-encoding-sniffer）
    // 会 require() 一个 ESM 模块，在本项目的 Node 版本下直接起不来 worker。
    environment: 'happy-dom',
    include: ['src/**/*.spec.ts'],
  },
})

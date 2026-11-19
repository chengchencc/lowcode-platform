import { defineConfig, devices } from '@playwright/test'

/**
 * E2E 配置。
 *
 * 服务由 scripts/e2e.sh 启动（后端 8000 + Vite 5173），这里只负责浏览器侧。
 * 首轮 workers=1：多角色共享实例的用例需要确定性；数据命名空间稳定后再考虑并行。
 *
 * 浏览器选择：
 * - Windows 默认用系统 Edge（channel=msedge），无需下载 200MB+ 的 Chromium。
 * - 其他平台默认用 Playwright 自带 Chromium（需 `npx playwright install chromium`）。
 * - 覆盖：E2E_BROWSER_CHANNEL=chrome / msedge；设为 bundled 强制用自带 Chromium。
 */
const requestedChannel = process.env.E2E_BROWSER_CHANNEL
const defaultChannel = process.platform === 'win32' ? 'msedge' : undefined
const channel =
  requestedChannel === 'bundled' || requestedChannel === 'chromium'
    ? undefined
    : (requestedChannel ?? defaultChannel)

export default defineConfig({
  testDir: './specs',
  outputDir: '../.runtime/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ['list'],
    ['html', { outputFolder: '../.runtime/playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // 视频需要额外的 ffmpeg 下载；失败时 trace + screenshot 已足够定位。
    // 需要录屏时：E2E_VIDEO=1（并先 npx playwright install ffmpeg）。
    video: process.env.E2E_VIDEO === '1' ? 'retain-on-failure' : 'off',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: channel ? `system-${channel}` : 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(channel ? { channel } : {}),
      },
    },
  ],
})

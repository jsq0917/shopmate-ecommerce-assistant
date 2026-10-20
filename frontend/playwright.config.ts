import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright 端到端配置。
 *
 * - `PLAYWRIGHT_BASE_URL`：被测前端地址（默认 http://localhost:5173，即 vite dev server）。
 * - webServer 默认启动 `npm run dev`；可用 `VITE_API_PROXY_TARGET` 指向本地/容器 API。
 * - 运行前置条件见 e2e/README.md（API 必须已经可用）。
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'on-first-retry',
    video: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      // 默认复用 Windows 预装的 Edge（msedge 通道），免去 170MB+ 的浏览器下载；
      // 如需独立 chromium：执行 `npx playwright install chromium` 后删除此行 channel。
      use: {
        ...devices['Desktop Chrome'],
        channel: 'msedge',
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      VITE_DEV_PORT: process.env.VITE_DEV_PORT ?? '5173',
      VITE_API_PROXY_TARGET: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
})

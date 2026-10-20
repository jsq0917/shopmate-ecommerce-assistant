/// <reference types="node" />
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

/**
 * Vite + Vitest 共享配置。
 *
 * 开发服务器默认把 `/api` 代理到后端（默认 http://localhost:8000，可用
 * VITE_API_PROXY_TARGET 覆盖），使前端与 API 同源：cookie、CORS 与 SSE
 * 都不需要额外配置。生产环境由 web/nginx.conf 做同样的反代。
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: Number(process.env.VITE_DEV_PORT ?? 5173),
    host: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        // 后端把登录相关 cookie（shopmate_refresh / shopmate_csrf）的 Path 设为
        // /api/v1/auth：浏览器只在该路径下携带 cookie，且页面 JS 在 / 下读不到
        // shopmate_csrf，导致静默刷新永远拿不到 CSRF 头、刷新页面必然回到登录页。
        // 这里把 Path 重写为 /；生产环境由 web/nginx.conf 的 proxy_cookie_path 同样处理。
        configure(proxy) {
          proxy.on('proxyRes', (proxyRes) => {
            const cookies = proxyRes.headers['set-cookie']
            if (!cookies) return
            proxyRes.headers['set-cookie'] = cookies.map((cookie) =>
              cookie.replace(/path=\/api\/v1\/auth(?=;|$)/i, 'path=/'),
            )
          })
        },
      },
    },
  },
  preview: {
    port: Number(process.env.VITE_PREVIEW_PORT ?? 4173),
    host: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
})

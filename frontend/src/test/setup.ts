import { beforeEach } from 'vitest'

/**
 * Vitest 全局 setup。
 *
 * 说明：
 * - Element Plus 组件多数通过全局安装使用，这里挂载完整插件，保证组件测试
 *   能像运行时一样解析 ElMessage 等全局能力。
 * - jsdom 没有 matchMedia / IntersectionObserver 等浏览器 API，Element Plus
 *   的部分组件（响应式菜单、ElTable 虚拟滚动等）会用到，这里做最小兜底，
 *   避免测试因环境差异失败，而不是给被测组件开后门。
 */

if (typeof window !== 'undefined') {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia
  }

  if (!('IntersectionObserver' in window)) {
    class IntersectionObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return []
      }
    }
    ;(window as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
      IntersectionObserverStub
  }

  if (!('ResizeObserver' in window)) {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(window as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub
  }
}

// 每个用例之间清理 DOM，避免组件泄漏影响后续用例。
beforeEach(() => {
  document.body.innerHTML = ''
})

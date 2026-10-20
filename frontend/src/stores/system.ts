/**
 * 系统元信息（合成数据标识）。用于全局 Synthetic 横幅（PRD F-24 / US-A06）。
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import { systemApi } from '@/api/endpoints'
import type { SystemMetaData } from '@/api/types'

export const useSystemStore = defineStore('system', () => {
  const meta = ref<SystemMetaData | null>(null)
  const loaded = ref(false)

  async function load(): Promise<void> {
    if (loaded.value) return
    loaded.value = true
    try {
      meta.value = await systemApi.meta()
    } catch {
      meta.value = null
    }
  }

  return { meta, loaded, load }
})

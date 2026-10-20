<script setup lang="ts">
import { onMounted } from 'vue'

import AppShell from '@/components/common/AppShell.vue'
import { useSystemStore } from '@/stores/system'

onMounted(() => {
  void useSystemStore().load()
})
</script>

<template>
  <AppShell />
</template>

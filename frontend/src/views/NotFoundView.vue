<script setup lang="ts">
/** 404 页面。 */
import { useRouter } from 'vue-router'
import { ElButton, ElResult } from 'element-plus'

const router = useRouter()
</script>

<template>
  <div class="sm-page sm-not-found">
    <ElResult icon="warning" title="404" sub-title="页面不存在或已被移动。">
      <template #extra>
        <ElButton type="primary" @click="router.push('/')">返回智能客服</ElButton>
      </template>
    </ElResult>
  </div>
</template>

<style scoped>
.sm-not-found {
  padding-top: 48px;
}
</style>

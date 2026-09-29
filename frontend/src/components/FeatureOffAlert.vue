<template>
  <el-alert
    class="feature-off-alert"
    type="warning"
    show-icon
    :closable="false"
    :title="`${moduleName}未启用（flag ${flagId} 关闭）`"
    description="开关关闭时后端按 feature-first 返回 400；开启后再试。"
  />
</template>

<script setup lang="ts">
defineProps<{
  moduleName: string
  flagId: string
}>()
</script>

<style scoped>
.feature-off-alert {
  margin-bottom: 12px;
}
</style>

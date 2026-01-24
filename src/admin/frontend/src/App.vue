<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import MainLayout from './layouts/MainLayout.vue'

const route = useRoute()
const authStore = useAuthStore()

// 判断是否需要显示主布局
const showLayout = computed(() => {
  return authStore.isAuthenticated && route.name !== 'Login'
})
</script>

<template>
  <MainLayout v-if="showLayout" />
  <router-view v-else />
</template>

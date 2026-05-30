<script setup lang="ts">
withDefaults(
  defineProps<{
    open: boolean
    title: string
    confirmText?: string
    cancelText?: string
    loading?: boolean
  }>(),
  {
    confirmText: '保存',
    cancelText: '取消',
    loading: false,
  }
)

const emit = defineEmits<{
  close: []
  confirm: []
}>()
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="emit('close')"></div>
    <div class="relative w-full max-w-lg bg-night-900 border border-gray-700 rounded-2xl shadow-2xl p-6">
      <h2 class="text-2xl font-bold text-white mb-6">{{ title }}</h2>
      <div>
        <slot />
      </div>
      <div class="flex gap-3 mt-8 justify-end">
        <button
          class="px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
          @click="emit('close')"
        >
          {{ cancelText }}
        </button>
        <button
          class="px-6 py-2 bg-sakura-500 hover:bg-sakura-600 text-white rounded-lg font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="loading"
          @click="emit('confirm')"
        >
          {{ loading ? '处理中...' : confirmText }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    open: boolean
    title: string
    message: string
    confirmText?: string
    cancelText?: string
    loading?: boolean
    danger?: boolean
  }>(),
  {
    confirmText: '确认',
    cancelText: '取消',
    loading: false,
    danger: false,
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
    <div class="relative w-full max-w-md bg-night-900 border border-gray-700 rounded-2xl shadow-2xl p-6">
      <h3 class="text-xl font-bold text-white mb-3">{{ title }}</h3>
      <p class="text-sm text-gray-300">{{ message }}</p>
      <div class="mt-6 flex justify-end gap-3">
        <button
          class="px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
          @click="emit('close')"
        >
          {{ cancelText }}
        </button>
        <button
          class="px-5 py-2 rounded-lg text-white font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :class="danger ? 'bg-red-500 hover:bg-red-600' : 'bg-amber-500 hover:bg-amber-600'"
          :disabled="loading"
          @click="emit('confirm')"
        >
          {{ loading ? '处理中...' : confirmText }}
        </button>
      </div>
    </div>
  </div>
</template>

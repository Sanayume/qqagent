<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    type?: 'error' | 'success' | 'info'
    message: string
    closable?: boolean
  }>(),
  {
    type: 'info',
    closable: true,
  }
)

const emit = defineEmits<{
  close: []
}>()

const toneClass =
  props.type === 'error'
    ? 'border-red-300 bg-red-50 text-red-700'
    : props.type === 'success'
      ? 'border-green-300 bg-green-50 text-green-700'
      : 'border-blue-300 bg-blue-50 text-blue-700'
</script>

<template>
  <div class="rounded-lg border px-4 py-3 text-sm flex items-center gap-2" :class="toneClass">
    <span class="font-medium">{{ message }}</span>
    <button v-if="closable" class="ml-auto text-current/80 hover:text-current" @click="emit('close')">
      ×
    </button>
  </div>
</template>

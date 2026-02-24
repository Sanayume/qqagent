<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '../api'

const content = ref('')
const originalContent = ref('')
const loading = ref(false)
const saving = ref(false)

const hasChanges = computed(() => content.value !== originalContent.value)

async function fetchConfig() {
  loading.value = true
  try {
    const res = await api.get('/api/config')
    content.value = res.data.content
    originalContent.value = res.data.content
  } catch (e: any) {
    console.error(e)
    alert('加载配置失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    await api.post('/api/config', { content: content.value })
    originalContent.value = content.value
    alert('配置已保存 (旧配置已自动备份)')
  } catch (e: any) {
    console.error(e)
    alert('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

onMounted(fetchConfig)
</script>

<template>
  <div class="h-full flex flex-col p-6">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-4">
        <h1 class="text-3xl font-bold text-white">配置管理</h1>
        <div class="text-gray-400 text-sm flex items-center gap-2">
          <span>config.yaml</span>
          <span v-if="hasChanges" class="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded-full">● 未保存更改</span>
        </div>
      </div>
      
      <div class="flex gap-3">
        <button 
          @click="fetchConfig" 
          :disabled="loading"
          class="px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
        >
          🔄 刷新
        </button>
        <button 
          @click="saveConfig"
          :disabled="!hasChanges || saving"
          class="px-6 py-2 bg-gradient-to-r from-miku-500 to-miku-600 text-white rounded-xl font-bold hover:shadow-lg hover:shadow-miku-500/20 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <span>💾</span> {{ saving ? '保存中...' : '保存配置' }}
        </button>
      </div>
    </div>

    <!-- 编辑器区域 -->
    <div class="flex-1 bg-night-900/50 backdrop-blur rounded-2xl border border-sakura-500/10 relative overflow-hidden group">
      <div v-if="loading" class="absolute inset-0 flex items-center justify-center z-10 bg-night-900/50">
        <div class="text-miku-400 animate-pulse">加载中...</div>
      </div>

      <textarea
        v-model="content"
        class="w-full h-full bg-transparent text-gray-200 font-mono text-sm p-6 outline-none resize-none custom-scrollbar leading-relaxed"
        spellcheck="false"
      ></textarea>
      
      <!-- 简单的行号装饰 (视觉效果) -->
      <div class="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-sakura-500/20 to-miku-500/20 opacity-0 group-hover:opacity-100 transition-opacity"></div>
    </div>
    
    <div class="mt-4 text-xs text-gray-500 flex justify-between">
      <p>⚠️ 修改配置可能需要重启 Agent 才能完全生效。</p>
      <p>系统会自动保留最近 10 次的配置备份。</p>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 8px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.1);
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

textarea {
  tab-size: 2;
}
</style>

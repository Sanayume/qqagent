<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '../api'

const presets = ref<string[]>([])
const currentPresetName = ref<string | null>(null)
const currentContent = ref<string>('')
const loading = ref(false)
const saving = ref(false)
const originalContent = ref('')

// 是否有未保存的更改
const hasChanges = computed(() => currentContent.value !== originalContent.value)

async function fetchPresets() {
  loading.value = true
  try {
    const res = await api.get('/api/presets')
    presets.value = res.data
    
    // 如果列表不为空且未选中，默认选第一个
    if (!currentPresetName.value && presets.value.length > 0) {
      const first = presets.value[0]
      if (first) selectPreset(first)
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function selectPreset(name: string) {
  if (hasChanges.value) {
    if (!confirm('当前有未保存的更改，确定要切换吗？')) return
  }
  
  loading.value = true
  currentPresetName.value = name
  try {
    const res = await api.get(`/api/presets/${name}`)
    currentContent.value = res.data.content
    originalContent.value = res.data.content
  } catch (e) {
    console.error(e)
    alert('加载预设失败')
  } finally {
    loading.value = false
  }
}

async function savePreset() {
  if (!currentPresetName.value) return
  
  saving.value = true
  try {
    await api.post(`/api/presets/${currentPresetName.value}`, {
      content: currentContent.value
    })
    originalContent.value = currentContent.value
    alert('保存成功 ✨')
  } catch (e: any) {
    alert(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function createPreset() {
  const name = prompt('请输入新预设名称 (不含 .yaml):')
  if (!name) return
  
  // 简单的校验
  if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(name)) {
    alert('名称只能包含字母、数字、下划线或中文')
    return
  }
  
  // 创建一个空模板
  const template = `system_prompt: |
  你是一个可爱的 AI 助手...

settings:
  model: gemini-pro
  temperature: 0.7
`
  
  try {
    await api.post(`/api/presets/${name}`, { content: template })
    presets.value.push(name)
    selectPreset(name)
  } catch (e: any) {
    alert(e.response?.data?.detail || '创建失败')
  }
}

async function deletePreset() {
  if (!currentPresetName.value) return
  if (!confirm(`确定要删除预设 "${currentPresetName.value}" 吗？此操作不可恢复！`)) return
  
  try {
    await api.delete(`/api/presets/${currentPresetName.value}`)
    // 从列表移除
    presets.value = presets.value.filter(p => p !== currentPresetName.value)
    
    // 如果还有其他预设，选中第一个；否则清空
    if (presets.value.length > 0) {
      // 重置 hasChanges 避免选中触发 confirm
      currentContent.value = ''
      originalContent.value = ''
      const first = presets.value[0]
      if (first) selectPreset(first)
    } else {
      currentPresetName.value = null
      currentContent.value = ''
      originalContent.value = ''
    }
  } catch (e) {
    console.error(e)
    alert('删除失败')
  }
}

onMounted(fetchPresets)
</script>

<template>
  <div class="h-full flex gap-6 p-6 overflow-hidden">
    <!-- 左侧列表 -->
    <div class="w-64 flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold text-white">预设列表</h2>
        <button 
          @click="createPreset" 
          class="p-2 bg-gradient-to-r from-sakura-500 to-sakura-600 rounded-lg text-white hover:shadow-lg transition-all"
          title="新建预设"
        >
          ➕
        </button>
      </div>

      <div class="flex-1 bg-night-900/50 backdrop-blur rounded-2xl border border-sakura-500/10 p-3 overflow-y-auto custom-scrollbar">
        <div 
          v-for="name in presets" 
          :key="name"
          class="flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all mb-2 group"
          :class="currentPresetName === name ? 'bg-sakura-500/20 text-white' : 'text-gray-400 hover:bg-white/5'"
          @click="selectPreset(name)"
        >
          <span class="text-xl">📄</span>
          <span class="truncate font-medium">{{ name }}</span>
        </div>
      </div>
    </div>

    <!-- 右侧编辑区 -->
    <div class="flex-1 flex flex-col bg-night-900/50 backdrop-blur rounded-2xl border border-sakura-500/10 overflow-hidden relative">
      <div v-if="currentPresetName" class="h-full flex flex-col">
        <!-- 工具栏 -->
        <div class="p-4 border-b border-white/5 flex items-center justify-between bg-white/5">
          <div class="flex items-center gap-4">
            <span class="text-lg font-bold text-gray-200">{{ currentPresetName }}.yaml</span>
            <span v-if="hasChanges" class="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded-full">● 未保存更改</span>
          </div>
          
          <div class="flex gap-3">
            <button 
              @click="deletePreset"
              class="px-4 py-2 rounded-lg text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors flex items-center gap-2"
            >
              <span>🗑️</span> 删除
            </button>
            <button 
              @click="savePreset"
              :disabled="!hasChanges || saving"
              class="px-6 py-2 bg-gradient-to-r from-miku-500 to-miku-600 text-white rounded-lg font-bold hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
            >
              <span>💾</span> {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>

        <!-- 编辑器 -->
        <div class="flex-1 relative">
          <textarea 
            v-model="currentContent"
            class="absolute inset-0 w-full h-full bg-transparent text-gray-200 font-mono text-sm p-4 outline-none resize-none custom-scrollbar leading-relaxed"
            spellcheck="false"
          ></textarea>
        </div>
      </div>
      
      <!-- 空状态 -->
      <div v-else class="h-full flex flex-col items-center justify-center text-gray-500">
        <div class="text-6xl mb-4 opacity-20">📝</div>
        <p>请选择或创建一个预设文件</p>
      </div>
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

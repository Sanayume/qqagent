<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import api from '../api'
import InlineNotice from '../components/InlineNotice.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const presets = ref<string[]>([])
const currentPresetName = ref<string | null>(null)
const currentContent = ref<string>('')
const loading = ref(false)
const saving = ref(false)
const originalContent = ref('')
const errorMsg = ref('')
const successMsg = ref('')
const deleteModalOpen = ref(false)
const unsavedModalOpen = ref(false)
const newPresetName = ref('')
const pendingSelectName = ref<string | null>(null)
const searchQuery = ref('')

// 是否有未保存的更改
const hasChanges = computed(() => currentContent.value !== originalContent.value)
const filteredPresets = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return presets.value
  return presets.value.filter((name) => name.toLowerCase().includes(query))
})

function resetEditorState() {
  currentPresetName.value = null
  currentContent.value = ''
  originalContent.value = ''
}

async function fetchPresets() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.get('/api/presets')
    presets.value = res.data

    // 如果列表不为空且未选中，默认选第一个
    if (!currentPresetName.value && presets.value.length > 0) {
      const first = presets.value[0]
      if (first) selectPreset(first)
    }
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || '加载预设列表失败'
  } finally {
    loading.value = false
  }
}

async function selectPreset(name: string) {
  errorMsg.value = ''
  loading.value = true
  currentPresetName.value = name
  try {
    const res = await api.get(`/api/presets/${name}`)
    currentContent.value = res.data.content
    originalContent.value = res.data.content
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || '加载预设失败'
  } finally {
    loading.value = false
  }
}

function requestSelectPreset(name: string) {
  if (name === currentPresetName.value) return
  if (hasChanges.value) {
    pendingSelectName.value = name
    unsavedModalOpen.value = true
    return
  }
  selectPreset(name)
}

function confirmDiscardAndSwitch() {
  if (!pendingSelectName.value) return
  unsavedModalOpen.value = false
  const target = pendingSelectName.value
  pendingSelectName.value = null
  selectPreset(target)
}

async function savePreset() {
  if (!currentPresetName.value) return

  errorMsg.value = ''
  successMsg.value = ''
  saving.value = true
  try {
    await api.post(`/api/presets/${currentPresetName.value}`, {
      content: currentContent.value
    })
    originalContent.value = currentContent.value
    successMsg.value = `已保存 ${currentPresetName.value}.yaml`
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

async function createPreset() {
  const name = newPresetName.value.trim()
  if (!name) {
    errorMsg.value = '请输入预设名称'
    return
  }
  if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(name)) {
    errorMsg.value = '名称只能包含字母、数字、下划线或中文'
    return
  }

  // 创建一个空模板
  const template = `system_prompt: |
  你是一个可爱的 AI 助手...

settings:
  model: gemini-pro
  temperature: 0.7
`

  errorMsg.value = ''
  successMsg.value = ''
  try {
    await api.post(`/api/presets/${name}`, { content: template })
    newPresetName.value = ''
    await fetchPresets()
    await selectPreset(name)
    successMsg.value = `已创建 ${name}.yaml`
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || '创建失败'
  }
}

async function deletePreset() {
  if (!currentPresetName.value) return
  errorMsg.value = ''
  successMsg.value = ''
  const deletingName = currentPresetName.value
  try {
    await api.delete(`/api/presets/${deletingName}`)
    presets.value = presets.value.filter(p => p !== deletingName)

    if (presets.value.length > 0) {
      resetEditorState()
      const first = presets.value[0]
      if (first) selectPreset(first)
    } else {
      resetEditorState()
    }
    successMsg.value = `已删除 ${deletingName}.yaml`
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || '删除失败'
  } finally {
    deleteModalOpen.value = false
  }
}

function resetCurrentChanges() {
  currentContent.value = originalContent.value
}

function handleShortcutSave(event: KeyboardEvent) {
  const isSave = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's'
  if (!isSave) return
  event.preventDefault()
  if (!saving.value && hasChanges.value && currentPresetName.value) {
    savePreset()
  }
}

onMounted(() => {
  fetchPresets()
  window.addEventListener('keydown', handleShortcutSave)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleShortcutSave)
})
</script>

<template>
  <div class="h-full flex gap-6 p-6 overflow-hidden">
    <!-- 左侧列表 -->
    <div class="w-72 flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold text-kivotos-navy">预设列表</h2>
        <span class="text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-600">{{ presets.length }}</span>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-3 flex items-center gap-2">
        <input
          v-model="newPresetName"
          type="text"
          class="flex-1 px-3 py-2 rounded-lg border border-gray-200 text-sm outline-none focus:border-kivotos-cyan"
          placeholder="新预设名"
          @keydown.enter="createPreset"
        >
        <button
          @click="createPreset"
          class="px-3 py-2 rounded-lg bg-kivotos-navy text-white text-sm font-bold hover:bg-slate-800"
        >
          新建
        </button>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-3">
        <input
          v-model="searchQuery"
          type="text"
          class="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm outline-none focus:border-kivotos-cyan"
          placeholder="搜索预设名"
        >
      </div>

      <InlineNotice v-if="errorMsg" type="error" :message="errorMsg" @close="errorMsg = ''" />
      <InlineNotice v-if="successMsg" type="success" :message="successMsg" @close="successMsg = ''" />

      <div class="flex-1 bg-white rounded-2xl border border-gray-200 p-3 overflow-y-auto custom-scrollbar">
        <div
          v-for="name in filteredPresets"
          :key="name"
          class="flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all mb-2 group"
          :class="currentPresetName === name ? 'bg-kivotos-cyan/15 text-kivotos-navy border border-kivotos-cyan/30' : 'text-gray-600 hover:bg-slate-50 border border-transparent'"
          @click="requestSelectPreset(name)"
        >
          <span class="text-base">📄</span>
          <span class="truncate font-medium">{{ name }}</span>
        </div>
        <div v-if="!loading && presets.length === 0" class="text-sm text-gray-400 p-2">暂无预设</div>
        <div v-else-if="!loading && filteredPresets.length === 0" class="text-sm text-gray-400 p-2">没有匹配的预设</div>
      </div>
    </div>

    <!-- 右侧编辑区 -->
    <div class="flex-1 flex flex-col bg-white rounded-2xl border border-gray-200 overflow-hidden relative">
      <div v-if="loading" class="h-full flex items-center justify-center text-gray-500">加载中...</div>
      <div v-else-if="currentPresetName" class="h-full flex flex-col">
        <!-- 工具栏 -->
        <div class="p-4 border-b border-gray-200 flex items-center justify-between bg-slate-50">
          <div class="flex items-center gap-4">
            <span class="text-lg font-bold text-kivotos-navy">{{ currentPresetName }}.yaml</span>
            <span v-if="hasChanges" class="text-xs text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">未保存更改</span>
          </div>

          <div class="flex gap-3">
            <button
              @click="resetCurrentChanges"
              :disabled="!hasChanges || saving"
              class="px-4 py-2 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              还原
            </button>
            <button
              @click="deleteModalOpen = true"
              class="px-4 py-2 rounded-lg text-red-500 hover:bg-red-50 transition-colors flex items-center gap-2"
            >
              删除
            </button>
            <button
              @click="savePreset"
              :disabled="!hasChanges || saving"
              class="px-6 py-2 bg-kivotos-navy text-white rounded-lg font-bold hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>

        <!-- 编辑器 -->
        <div class="flex-1 relative">
          <textarea
            v-model="currentContent"
            class="absolute inset-0 w-full h-full bg-white text-gray-800 font-mono text-sm p-4 outline-none resize-none custom-scrollbar leading-relaxed"
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

    <ConfirmDialog
      :open="deleteModalOpen && Boolean(currentPresetName)"
      title="确认删除"
      :message="currentPresetName ? `确定删除预设 ${currentPresetName} 吗？此操作不可恢复。` : ''"
      confirm-text="删除"
      cancel-text="取消"
      danger
      @close="deleteModalOpen = false"
      @confirm="deletePreset"
    />

    <ConfirmDialog
      :open="unsavedModalOpen"
      title="有未保存更改"
      message="当前编辑内容尚未保存，切换预设会丢失这些修改。"
      confirm-text="丢弃并切换"
      cancel-text="取消"
      @close="unsavedModalOpen = false; pendingSelectName = null"
      @confirm="confirmDiscardAndSwitch"
    />
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

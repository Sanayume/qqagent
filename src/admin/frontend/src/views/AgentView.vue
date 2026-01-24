<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import {
  Bot,
  RefreshCw,
  Trash2,
  Clock,
  MessageSquare,
  AlertCircle,
  Database,
  Wrench,
  Check,
  X
} from 'lucide-vue-next'

interface AgentStatus {
  running: boolean
  model: string | null
  base_url: string | null
  tools_count: number
  tools: string[]
  session_count: number
  stats: {
    uptime: string
    uptime_seconds: number
    messages_processed: number
    errors_count: number
    last_message_time: string | null
  }
}

interface Session {
  session_id: string
  message_count: number
}

const status = ref<AgentStatus | null>(null)
const sessions = ref<Session[]>([])
const loading = ref(false)
const reloading = ref(false)
const error = ref('')
const successMsg = ref('')

// LLM Config form
const llmForm = ref({
  model: '',
  base_url: '',
  api_key: ''
})

const showLLMForm = ref(false)

async function fetchStatus() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/agent/status')
    status.value = res.data
    llmForm.value.model = res.data.model || ''
    llmForm.value.base_url = res.data.base_url || ''
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Failed to fetch status'
  } finally {
    loading.value = false
  }
}

async function fetchSessions() {
  try {
    const res = await axios.get('/api/agent/sessions')
    sessions.value = res.data.sessions || []
  } catch (e) {
    console.error('Failed to fetch sessions', e)
  }
}

async function reloadLLM() {
  reloading.value = true
  error.value = ''
  successMsg.value = ''
  try {
    const payload: any = {}
    if (llmForm.value.model) payload.model = llmForm.value.model
    if (llmForm.value.base_url) payload.base_url = llmForm.value.base_url
    if (llmForm.value.api_key) payload.api_key = llmForm.value.api_key

    await axios.post('/api/agent/llm/reload', payload)
    successMsg.value = 'LLM config reloaded!'
    showLLMForm.value = false
    await fetchStatus()
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Failed to reload LLM'
  } finally {
    reloading.value = false
  }
}

async function clearSession(sessionId: string) {
  if (!confirm(`Clear session ${sessionId}?`)) return
  try {
    await axios.delete(`/api/agent/sessions/${encodeURIComponent(sessionId)}`)
    successMsg.value = `Session ${sessionId} cleared`
    await fetchSessions()
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Failed to clear session'
  }
}

async function clearAllSessions() {
  if (!confirm('Clear ALL sessions? This cannot be undone.')) return
  try {
    await axios.delete('/api/agent/sessions')
    successMsg.value = 'All sessions cleared'
    await fetchSessions()
    await fetchStatus()
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Failed to clear sessions'
  }
}

const uptimeFormatted = computed(() => {
  if (!status.value?.stats?.uptime) return 'N/A'
  return status.value.stats.uptime
})

onMounted(() => {
  fetchStatus()
  fetchSessions()
})
</script>

<template>
  <div class="h-full flex flex-col gap-6">

    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-3xl font-black text-kivotos-navy tracking-tight skew-x-[-5deg] uppercase">
          Agent Control
        </h2>
        <p class="text-kivotos-gray font-mono text-xs mt-1 font-bold">RUNTIME MANAGEMENT // STATUS</p>
      </div>
      <button
        @click="fetchStatus(); fetchSessions()"
        class="flex items-center gap-2 bg-white px-4 py-2 rounded-lg border border-kivotos-cyan shadow-sm hover:bg-kivotos-cyan/10 transition-colors"
        :disabled="loading"
      >
        <RefreshCw :size="16" class="text-kivotos-cyan" :class="{ 'animate-spin': loading }" />
        <span class="font-mono font-bold text-kivotos-navy text-sm">Refresh</span>
      </button>
    </div>

    <!-- Messages -->
    <div v-if="error" class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
      <AlertCircle :size="18" />
      <span class="font-medium">{{ error }}</span>
      <button @click="error = ''" class="ml-auto"><X :size="16" /></button>
    </div>
    <div v-if="successMsg" class="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg flex items-center gap-2">
      <Check :size="18" />
      <span class="font-medium">{{ successMsg }}</span>
      <button @click="successMsg = ''" class="ml-auto"><X :size="16" /></button>
    </div>

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

      <!-- Status Card -->
      <div class="lg:col-span-2 bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <div class="flex items-center gap-3 mb-6">
          <div class="w-10 h-10 bg-kivotos-cyan/10 rounded-lg flex items-center justify-center">
            <Bot :size="20" class="text-kivotos-cyan" />
          </div>
          <div>
            <h3 class="font-bold text-kivotos-navy">Agent Status</h3>
            <p class="text-xs text-gray-500">Real-time agent information</p>
          </div>
          <div class="ml-auto flex items-center gap-2">
            <span class="w-3 h-3 rounded-full" :class="status?.running ? 'bg-green-500 animate-pulse' : 'bg-gray-300'"></span>
            <span class="font-bold text-sm" :class="status?.running ? 'text-green-600' : 'text-gray-500'">
              {{ status?.running ? 'RUNNING' : 'STOPPED' }}
            </span>
          </div>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6" v-if="status">
          <!-- Uptime -->
          <div class="bg-slate-50 rounded-xl p-4">
            <div class="flex items-center gap-2 text-gray-500 mb-1">
              <Clock :size="14" />
              <span class="text-xs font-bold uppercase">Uptime</span>
            </div>
            <p class="font-mono font-bold text-kivotos-navy">{{ uptimeFormatted }}</p>
          </div>

          <!-- Messages -->
          <div class="bg-slate-50 rounded-xl p-4">
            <div class="flex items-center gap-2 text-gray-500 mb-1">
              <MessageSquare :size="14" />
              <span class="text-xs font-bold uppercase">Messages</span>
            </div>
            <p class="font-mono font-bold text-kivotos-navy">{{ status.stats?.messages_processed || 0 }}</p>
          </div>

          <!-- Errors -->
          <div class="bg-slate-50 rounded-xl p-4">
            <div class="flex items-center gap-2 text-gray-500 mb-1">
              <AlertCircle :size="14" />
              <span class="text-xs font-bold uppercase">Errors</span>
            </div>
            <p class="font-mono font-bold" :class="status.stats?.errors_count > 0 ? 'text-red-600' : 'text-kivotos-navy'">
              {{ status.stats?.errors_count || 0 }}
            </p>
          </div>

          <!-- Sessions -->
          <div class="bg-slate-50 rounded-xl p-4">
            <div class="flex items-center gap-2 text-gray-500 mb-1">
              <Database :size="14" />
              <span class="text-xs font-bold uppercase">Sessions</span>
            </div>
            <p class="font-mono font-bold text-kivotos-navy">{{ status.session_count || 0 }}</p>
          </div>
        </div>

        <!-- Model Info -->
        <div class="border-t pt-4" v-if="status">
          <div class="flex items-center justify-between mb-4">
            <h4 class="font-bold text-sm text-gray-700">LLM Configuration</h4>
            <button
              @click="showLLMForm = !showLLMForm"
              class="text-xs px-3 py-1 bg-kivotos-cyan/10 text-kivotos-cyan rounded-lg font-bold hover:bg-kivotos-cyan/20 transition-colors"
            >
              {{ showLLMForm ? 'Cancel' : 'Edit' }}
            </button>
          </div>

          <div v-if="!showLLMForm" class="grid grid-cols-2 gap-4">
            <div>
              <span class="text-xs text-gray-500">Model</span>
              <p class="font-mono text-sm font-bold text-kivotos-navy">{{ status.model || 'N/A' }}</p>
            </div>
            <div>
              <span class="text-xs text-gray-500">Base URL</span>
              <p class="font-mono text-sm text-kivotos-navy truncate">{{ status.base_url || 'Default' }}</p>
            </div>
          </div>

          <!-- Edit Form -->
          <div v-else class="space-y-4">
            <div>
              <label class="text-xs text-gray-500 block mb-1">Model</label>
              <input
                v-model="llmForm.model"
                type="text"
                class="w-full px-3 py-2 border rounded-lg font-mono text-sm focus:ring-2 focus:ring-kivotos-cyan focus:border-transparent"
                placeholder="gpt-4o-mini"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500 block mb-1">Base URL (optional)</label>
              <input
                v-model="llmForm.base_url"
                type="text"
                class="w-full px-3 py-2 border rounded-lg font-mono text-sm focus:ring-2 focus:ring-kivotos-cyan focus:border-transparent"
                placeholder="https://api.openai.com/v1"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500 block mb-1">API Key (leave empty to keep current)</label>
              <input
                v-model="llmForm.api_key"
                type="password"
                class="w-full px-3 py-2 border rounded-lg font-mono text-sm focus:ring-2 focus:ring-kivotos-cyan focus:border-transparent"
                placeholder="sk-..."
              />
            </div>
            <button
              @click="reloadLLM"
              :disabled="reloading"
              class="w-full py-2 bg-kivotos-cyan text-white rounded-lg font-bold hover:bg-kivotos-cyan/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <RefreshCw :size="16" :class="{ 'animate-spin': reloading }" />
              {{ reloading ? 'Reloading...' : 'Reload LLM Config' }}
            </button>
          </div>
        </div>

        <!-- Tools -->
        <div class="border-t pt-4 mt-4" v-if="status?.tools?.length">
          <div class="flex items-center gap-2 mb-3">
            <Wrench :size="16" class="text-gray-500" />
            <h4 class="font-bold text-sm text-gray-700">Available Tools ({{ status.tools_count }})</h4>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="tool in status.tools"
              :key="tool"
              class="px-2 py-1 bg-slate-100 text-slate-700 rounded text-xs font-mono"
            >
              {{ tool }}
            </span>
          </div>
        </div>
      </div>

      <!-- Sessions Panel -->
      <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-2">
            <Database :size="18" class="text-kivotos-pink" />
            <h3 class="font-bold text-kivotos-navy">Sessions</h3>
          </div>
          <button
            v-if="sessions.length > 0"
            @click="clearAllSessions"
            class="text-xs px-2 py-1 bg-red-50 text-red-600 rounded font-bold hover:bg-red-100 transition-colors"
          >
            Clear All
          </button>
        </div>

        <div v-if="sessions.length === 0" class="text-center py-8 text-gray-400">
          <Database :size="32" class="mx-auto mb-2 opacity-50" />
          <p class="text-sm">No active sessions</p>
        </div>

        <div v-else class="space-y-2 max-h-[400px] overflow-y-auto">
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="flex items-center justify-between p-3 bg-slate-50 rounded-lg group hover:bg-slate-100 transition-colors"
          >
            <div class="min-w-0 flex-1">
              <p class="font-mono text-xs text-kivotos-navy truncate" :title="session.session_id">
                {{ session.session_id }}
              </p>
              <p class="text-xs text-gray-500">{{ session.message_count }} messages</p>
            </div>
            <button
              @click="clearSession(session.session_id)"
              class="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors opacity-0 group-hover:opacity-100"
            >
              <Trash2 :size="14" />
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

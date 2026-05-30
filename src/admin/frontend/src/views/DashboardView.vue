<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Bot,
  Cable,
  Clock3,
  RefreshCw,
  Radio,
  Settings2,
  Terminal,
  Waves,
  ShieldCheck,
} from 'lucide-vue-next'

import api, { buildWsUrl } from '../api'
import { useAuthStore } from '../stores/auth'

interface ReloadState {
  count: number
  last_at: string | null
  last_status: string
  last_detail: string
}

interface StatusPayload {
  agent: {
    status: string
    running: boolean
    uptime: string
    uptime_seconds: number
    model: string | null
    base_url: string | null
    voice_mode: string | null
    default_preset: string | null
    session_count: number
    messages_processed: number
    errors_count: number
    last_message_time: string | null
    fallback_models: string[]
    fallback_count: number
  }
  onebot: {
    mode: string | null
    connected: boolean
    forward_connected: boolean
    reverse_connected: boolean
    ws_url: string | null
    reverse_endpoint: string | null
    token_configured: boolean
  }
  telegram: {
    enabled: boolean
    running: boolean
    connected: boolean
    session_path: string | null
    has_proxy: boolean
    reconnect_attempt: number
    last_error: string | null
    last_error_at: string | null
    last_connected_at: string | null
    monitor_channels: string[]
    monitor_keywords: string[]
  }
  admin: {
    port: number
    static_ready: boolean
  }
  behavior: {
    allow_at: boolean
    allow_private: boolean
    allow_all_group: boolean
    bot_names: string[]
  }
  reloads: {
    env_reload: ReloadState
    config_reload: ReloadState
  }
  mcp: {
    count: number
    servers: string[]
  }
  presets: {
    count: number
    current: string | null
  }
}

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const status = ref<StatusPayload | null>(null)
const logs = ref<{ time: string; level: string; message: string }[]>([])
const currentTime = ref(new Date())
let statusTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null
let logWs: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let streamStopped = false

const summaryCards = computed(() => {
  if (!status.value) return []
  return [
    {
      title: 'Agent',
      value: status.value.agent.running ? 'RUNNING' : 'STOPPED',
      hint: status.value.agent.model || 'No model',
      ok: status.value.agent.running,
      icon: Bot,
    },
    {
      title: 'OneBot',
      value: status.value.onebot.connected ? 'CONNECTED' : 'DISCONNECTED',
      hint: status.value.onebot.mode || 'unknown',
      ok: status.value.onebot.connected,
      icon: Cable,
    },
    {
      title: 'Telegram',
      value: !status.value.telegram.enabled ? 'DISABLED' : status.value.telegram.connected ? 'CONNECTED' : 'RETRYING',
      hint: status.value.telegram.enabled ? `retry=${status.value.telegram.reconnect_attempt}` : 'not enabled',
      ok: status.value.telegram.enabled ? status.value.telegram.connected : true,
      icon: Radio,
    },
    {
      title: 'Reloads',
      value: `${status.value.reloads.env_reload?.count || 0}/${status.value.reloads.config_reload?.count || 0}`,
      hint: '.env / config.yaml',
      ok: (status.value.reloads.env_reload?.last_status || 'idle') !== 'error' && (status.value.reloads.config_reload?.last_status || 'idle') !== 'error',
      icon: RefreshCw,
    },
  ]
})

function levelClass(level: string) {
  switch ((level || '').toUpperCase()) {
    case 'ERROR':
    case 'CRITICAL':
      return 'text-red-300 border-red-500/30'
    case 'WARNING':
      return 'text-yellow-200 border-yellow-500/30'
    case 'SUCCESS':
      return 'text-green-300 border-green-500/30'
    default:
      return 'text-slate-200 border-white/10'
  }
}

async function fetchStatus() {
  loading.value = true
  try {
    const res = await api.get('/api/status')
    status.value = res.data
  } finally {
    loading.value = false
  }
}

function connectLogStream() {
  if (!authStore.token) return
  const url = buildWsUrl('/api/logs/stream', authStore.token)
  logWs = new WebSocket(url)
  logWs.onmessage = (event) => {
    try {
      const entry = JSON.parse(event.data)
      logs.value.unshift(entry)
      if (logs.value.length > 30) logs.value.pop()
    } catch {
      logs.value.unshift({ time: new Date().toLocaleTimeString(), level: 'INFO', message: String(event.data) })
      if (logs.value.length > 30) logs.value.pop()
    }
  }
  logWs.onclose = () => {
    if (!streamStopped) {
      reconnectTimer = setTimeout(() => connectLogStream(), 3000)
    }
  }
}

function formatTime(value: string | null | undefined) {
  if (!value) return '?'
  return new Date(value).toLocaleString()
}

onMounted(async () => {
  streamStopped = false
  await fetchStatus()
  connectLogStream()
  statusTimer = setInterval(fetchStatus, 5000)
  clockTimer = setInterval(() => {
    currentTime.value = new Date()
  }, 1000)
})

onUnmounted(() => {
  streamStopped = true
  if (statusTimer) clearInterval(statusTimer)
  if (clockTimer) clearInterval(clockTimer)
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (logWs) logWs.close()
})
</script>

<template>
  <div class="h-full flex flex-col gap-6">
    <div class="flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-3xl font-black text-kivotos-navy tracking-tight uppercase">System Overview</h2>
        <p class="text-kivotos-gray font-mono text-xs mt-1 font-bold">REAL RUNTIME STATUS // ADMIN CONSOLE</p>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex items-center gap-2 bg-white px-4 py-2 rounded-lg border border-gray-200 shadow-sm">
          <Clock3 class="text-kivotos-cyan" :size="16" />
          <span class="font-mono font-bold text-kivotos-navy">{{ currentTime.toLocaleTimeString() }}</span>
        </div>
        <button
          @click="fetchStatus"
          :disabled="loading"
          class="px-4 py-2 rounded-lg bg-kivotos-navy text-white font-bold flex items-center gap-2 hover:bg-slate-800 disabled:opacity-60"
        >
          <RefreshCw :size="16" :class="loading ? 'animate-spin' : ''" />
          Refresh
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <div
        v-for="card in summaryCards"
        :key="card.title"
        class="bg-white p-4 rounded-2xl border shadow-sm"
        :class="card.ok ? 'border-gray-100' : 'border-red-200'"
      >
        <div class="flex items-center justify-between">
          <p class="text-xs font-bold text-gray-500 uppercase tracking-wider">{{ card.title }}</p>
          <component :is="card.icon" :size="18" :class="card.ok ? 'text-kivotos-cyan' : 'text-red-400'" />
        </div>
        <p class="mt-3 text-2xl font-black text-kivotos-navy">{{ card.value }}</p>
        <p class="mt-1 text-xs text-gray-500 font-mono">{{ card.hint }}</p>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-6 flex-1 min-h-0">
      <div class="xl:col-span-2 flex flex-col gap-6 min-h-0">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section class="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <div class="flex items-center gap-2 mb-4">
              <Bot :size="18" class="text-kivotos-cyan" />
              <h3 class="font-black text-kivotos-navy">Agent Runtime</h3>
            </div>
            <div v-if="status" class="space-y-3 text-sm">
              <div class="flex items-center justify-between"><span class="text-gray-500">Model</span><span class="font-mono text-kivotos-navy">{{ status.agent.model || '?' }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Preset</span><span class="font-bold text-kivotos-navy">{{ status.agent.default_preset || '?' }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Voice Mode</span><span class="font-mono text-kivotos-navy">{{ status.agent.voice_mode || '?' }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Sessions</span><span class="font-black text-kivotos-navy">{{ status.agent.session_count }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Messages</span><span class="font-black text-kivotos-navy">{{ status.agent.messages_processed }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Errors</span><span class="font-black" :class="status.agent.errors_count ? 'text-red-500' : 'text-green-600'">{{ status.agent.errors_count }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Last Message</span><span class="font-mono text-xs text-kivotos-navy">{{ formatTime(status.agent.last_message_time) }}</span></div>
              <div>
                <div class="flex items-center justify-between mb-2"><span class="text-gray-500">Fallback LLM Models</span><span class="font-black text-kivotos-navy">{{ status.agent.fallback_count }}</span></div>
                <div class="flex flex-wrap gap-2">
                  <span v-for="model in status.agent.fallback_models" :key="model" class="px-2 py-1 rounded-lg bg-kivotos-cyan/10 text-kivotos-cyan text-xs font-mono">{{ model }}</span>
                  <span v-if="status.agent.fallback_models.length === 0" class="text-xs text-gray-400">No fallback models configured</span>
                </div>
              </div>
            </div>
          </section>

          <section class="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <div class="flex items-center gap-2 mb-4">
              <Cable :size="18" class="text-kivotos-pink" />
              <h3 class="font-black text-kivotos-navy">Transport Runtime</h3>
            </div>
            <div v-if="status" class="space-y-4 text-sm">
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="font-bold text-kivotos-navy">OneBot / NapCat</span>
                  <span class="px-2 py-1 rounded-lg text-xs font-bold" :class="status.onebot.connected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'">{{ status.onebot.connected ? 'Connected' : 'Disconnected' }}</span>
                </div>
                <div class="space-y-2 text-xs text-gray-600 font-mono">
                  <div>mode = {{ status.onebot.mode || '?' }}</div>
                  <div>forward = {{ status.onebot.forward_connected }}</div>
                  <div>reverse = {{ status.onebot.reverse_connected }}</div>
                  <div class="break-all">ws = {{ status.onebot.ws_url || '?' }}</div>
                  <div class="break-all">reverse = {{ status.onebot.reverse_endpoint || '?' }}</div>
                </div>
              </div>
              <div class="pt-3 border-t border-gray-100">
                <div class="flex items-center justify-between mb-2">
                  <span class="font-bold text-kivotos-navy">Telegram</span>
                  <span class="px-2 py-1 rounded-lg text-xs font-bold" :class="!status.telegram.enabled ? 'bg-gray-100 text-gray-500' : status.telegram.connected ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'">{{ !status.telegram.enabled ? 'Disabled' : status.telegram.connected ? 'Connected' : 'Retrying' }}</span>
                </div>
                <div class="space-y-2 text-xs text-gray-600 font-mono">
                  <div>session = {{ status.telegram.session_path || '?' }}</div>
                  <div>proxy = {{ status.telegram.has_proxy }}</div>
                  <div>attempt = {{ status.telegram.reconnect_attempt }}</div>
                  <div>last connected = {{ formatTime(status.telegram.last_connected_at) }}</div>
                  <div v-if="status.telegram.last_error" class="text-red-500 break-all">{{ status.telegram.last_error }}</div>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section class="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <div class="flex items-center gap-2 mb-4">
              <Waves :size="18" class="text-kivotos-blue" />
              <h3 class="font-black text-kivotos-navy">Hot Reload</h3>
            </div>
            <div v-if="status" class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="rounded-xl border p-4" :class="status.reloads.env_reload?.last_status === 'error' ? 'border-red-200 bg-red-50' : 'border-gray-100 bg-slate-50'">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-kivotos-navy">.env</span>
                  <span class="text-xs font-mono text-gray-500">{{ status.reloads.env_reload?.count || 0 }}</span>
                </div>
                <p class="mt-2 text-xs text-gray-600">{{ status.reloads.env_reload?.last_status || 'idle' }}</p>
                <p class="mt-1 text-xs font-mono text-gray-500">{{ formatTime(status.reloads.env_reload?.last_at) }}</p>
                <p class="mt-2 text-xs text-gray-500 break-all">{{ status.reloads.env_reload?.last_detail || 'No reload yet' }}</p>
              </div>
              <div class="rounded-xl border p-4" :class="status.reloads.config_reload?.last_status === 'error' ? 'border-red-200 bg-red-50' : 'border-gray-100 bg-slate-50'">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-kivotos-navy">config.yaml</span>
                  <span class="text-xs font-mono text-gray-500">{{ status.reloads.config_reload?.count || 0 }}</span>
                </div>
                <p class="mt-2 text-xs text-gray-600">{{ status.reloads.config_reload?.last_status || 'idle' }}</p>
                <p class="mt-1 text-xs font-mono text-gray-500">{{ formatTime(status.reloads.config_reload?.last_at) }}</p>
                <p class="mt-2 text-xs text-gray-500 break-all">{{ status.reloads.config_reload?.last_detail || 'No reload yet' }}</p>
              </div>
            </div>
          </section>

          <section class="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <div class="flex items-center gap-2 mb-4">
              <Settings2 :size="18" class="text-kivotos-yellow" />
              <h3 class="font-black text-kivotos-navy">Console + Behavior</h3>
            </div>
            <div v-if="status" class="space-y-3 text-sm">
              <div class="flex items-center justify-between"><span class="text-gray-500">Admin Port</span><span class="font-mono text-kivotos-navy">{{ status.admin.port }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Static Assets</span><span class="font-bold" :class="status.admin.static_ready ? 'text-green-600' : 'text-red-500'">{{ status.admin.static_ready ? 'Ready' : 'Missing' }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Allow @ Reply</span><span class="font-mono text-kivotos-navy">{{ status.behavior.allow_at }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Allow Private</span><span class="font-mono text-kivotos-navy">{{ status.behavior.allow_private }}</span></div>
              <div class="flex items-center justify-between"><span class="text-gray-500">Allow All Group</span><span class="font-mono text-kivotos-navy">{{ status.behavior.allow_all_group }}</span></div>
              <div>
                <div class="text-gray-500 mb-2">Bot Names</div>
                <div class="flex flex-wrap gap-2">
                  <span v-for="name in status.behavior.bot_names" :key="name" class="px-2 py-1 rounded-lg bg-kivotos-pink/10 text-kivotos-pink text-xs font-bold">{{ name }}</span>
                </div>
              </div>
            </div>
          </section>
        </div>

        <section class="bg-gradient-to-r from-kivotos-cyan to-kivotos-blue rounded-2xl p-6 text-white shadow-lg shadow-kivotos-cyan/20">
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div class="flex items-center gap-2 opacity-80 mb-2">
                <ShieldCheck :size="16" />
                <span class="text-xs font-mono tracking-widest uppercase font-bold">Control Summary</span>
              </div>
              <h3 class="text-3xl font-black italic mb-3">Web Console Now Tracks Real Runtime</h3>
              <p class="text-white/90 text-sm leading-relaxed max-w-2xl">
                OneBot, Telegram, fallback LLMs, hot reload results, and core agent counters are now surfaced from the live process instead of stale static assumptions.
              </p>
            </div>
            <div class="flex gap-3">
              <button @click="router.push('/logs')" class="bg-white text-kivotos-blue px-5 py-2 rounded-lg font-bold hover:bg-blue-50 transition-colors text-sm">View Logs</button>
              <button @click="router.push('/sandbox')" class="bg-kivotos-navy/40 text-white px-5 py-2 rounded-lg font-bold hover:bg-kivotos-navy/50 transition-colors text-sm border border-white/30">Open Sandbox</button>
            </div>
          </div>
        </section>
      </div>

      <section class="bg-kivotos-navy rounded-2xl p-1 shadow-xl flex flex-col min-h-0 overflow-hidden border border-kivotos-navy">
        <div class="bg-kivotos-navy px-4 py-2 flex items-center justify-between border-b border-white/10">
          <div class="flex items-center gap-2">
            <Terminal :size="14" class="text-kivotos-cyan" />
            <span class="text-xs font-mono font-bold text-white/80">LIVE FEED</span>
          </div>
          <div class="flex gap-1.5">
            <div class="w-2.5 h-2.5 rounded-full bg-red-500"></div>
            <div class="w-2.5 h-2.5 rounded-full bg-yellow-500"></div>
            <div class="w-2.5 h-2.5 rounded-full bg-green-500"></div>
          </div>
        </div>
        <div class="flex-1 bg-[#0f111a] p-4 font-mono text-xs overflow-y-auto custom-scrollbar">
          <div
            v-for="(entry, index) in logs"
            :key="index"
            class="mb-2 break-all border-l-2 pl-3 transition-colors"
            :class="levelClass(entry.level)"
          >
            <div class="flex items-center justify-between gap-2 mb-1">
              <span class="text-[10px] uppercase tracking-wide opacity-70">{{ entry.level }}</span>
              <span class="text-[10px] text-kivotos-gray">{{ entry.time }}</span>
            </div>
            <span class="leading-relaxed">{{ entry.message }}</span>
          </div>
          <div v-if="logs.length === 0" class="text-gray-600 italic text-center mt-10">
            Waiting for authenticated log stream...
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

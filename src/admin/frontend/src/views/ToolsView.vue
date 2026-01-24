<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import {
  Wrench,
  RefreshCw,
  ToggleLeft,
  ToggleRight,
  AlertCircle,
  Check,
  X,
  Shield,
  Server,
  ChevronDown,
  ChevronRight
} from 'lucide-vue-next'

interface Tool {
  name: string
  description: string
  category: string
  source: string
  source_name: string
  is_core: boolean
  enabled: boolean
  version: string
  author: string
  tags: string[]
  tool_description: string
}

interface ToolStatus {
  total: number
  enabled: number
  disabled: number
  core: number
  by_category: Record<string, { total: number; enabled: number }>
  by_source: Record<string, { total: number; enabled: number }>
}

interface MCPServer {
  total: number
  enabled: number
  tools: string[]
}

const tools = ref<Tool[]>([])
const status = ref<ToolStatus | null>(null)
const mcpServers = ref<Record<string, MCPServer>>({})
const expandedServers = ref<Set<string>>(new Set())
const loading = ref(false)
const error = ref('')
const successMsg = ref('')
const filter = ref<string>('all')
const viewMode = ref<'all' | 'builtin' | 'mcp'>('all')

const categoryLabels: Record<string, string> = {
  core: 'Core',
  utility: 'Utility',
  messaging: 'Messaging',
  search: 'Search',
  media: 'Media',
  custom: 'Custom'
}

async function fetchTools() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/tools')
    tools.value = res.data.tools || []
    status.value = res.data.status || null
    // Fetch MCP servers
    const mcpRes = await axios.get('/api/tools/mcp/servers')
    mcpServers.value = mcpRes.data.servers || {}
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Failed to fetch tools'
  } finally {
    loading.value = false
  }
}

async function toggleTool(tool: Tool) {
  if (tool.is_core) return

  try {
    await axios.post(`/api/tools/${tool.name}/toggle`, {
      enabled: !tool.enabled
    })
    tool.enabled = !tool.enabled
    successMsg.value = `${tool.name} ${tool.enabled ? 'enabled' : 'disabled'}`
    setTimeout(() => successMsg.value = '', 2000)
    // Refresh status
    const res = await axios.get('/api/tools/status')
    status.value = res.data
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Failed to toggle tool'
  }
}

const filteredTools = computed(() => {
  let result = tools.value

  // Filter by view mode
  if (viewMode.value === 'builtin') {
    result = result.filter(t => t.source === 'builtin')
  } else if (viewMode.value === 'mcp') {
    result = result.filter(t => t.source === 'mcp')
  }

  // Filter by status/category
  if (filter.value === 'all') return result
  if (filter.value === 'enabled') return result.filter(t => t.enabled)
  if (filter.value === 'disabled') return result.filter(t => !t.enabled)
  return result.filter(t => t.category === filter.value)
})

const builtinTools = computed(() => tools.value.filter(t => t.source === 'builtin'))
const mcpTools = computed(() => tools.value.filter(t => t.source === 'mcp'))

function toggleServer(name: string) {
  if (expandedServers.value.has(name)) {
    expandedServers.value.delete(name)
  } else {
    expandedServers.value.add(name)
  }
}

function getServerTools(serverName: string) {
  return tools.value.filter(t => t.source === 'mcp' && t.source_name === serverName)
}

const categories = computed(() => {
  const cats = new Set(tools.value.map(t => t.category))
  return Array.from(cats)
})

onMounted(() => {
  fetchTools()
})
</script>

<template>
  <div class="h-full flex flex-col gap-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-3xl font-black text-kivotos-navy tracking-tight skew-x-[-5deg] uppercase">
          Tools
        </h2>
        <p class="text-kivotos-gray font-mono text-xs mt-1 font-bold">BUILTIN & MCP TOOLS // MANAGEMENT</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- View Mode Toggle -->
        <div class="flex bg-slate-100 rounded-lg p-1">
          <button
            v-for="mode in ['all', 'builtin', 'mcp'] as const"
            :key="mode"
            @click="viewMode = mode"
            class="px-3 py-1.5 rounded-md text-xs font-bold transition-colors"
            :class="viewMode === mode ? 'bg-white text-kivotos-navy shadow-sm' : 'text-gray-500 hover:text-gray-700'"
          >
            {{ mode === 'all' ? 'All' : mode === 'builtin' ? 'Builtin' : 'MCP' }}
          </button>
        </div>
        <button
          @click="fetchTools"
          class="flex items-center gap-2 bg-white px-4 py-2 rounded-lg border border-kivotos-cyan shadow-sm hover:bg-kivotos-cyan/10 transition-colors"
          :disabled="loading"
        >
          <RefreshCw :size="16" class="text-kivotos-cyan" :class="{ 'animate-spin': loading }" />
          <span class="font-mono font-bold text-kivotos-navy text-sm">Refresh</span>
        </button>
      </div>
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
    </div>

    <!-- Status Cards -->
    <div class="grid grid-cols-2 md:grid-cols-6 gap-4" v-if="status">
      <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <p class="text-xs font-bold text-gray-500 uppercase">Total</p>
        <p class="text-2xl font-black text-kivotos-navy">{{ status.total }}</p>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <p class="text-xs font-bold text-gray-500 uppercase">Enabled</p>
        <p class="text-2xl font-black text-green-600">{{ status.enabled }}</p>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <p class="text-xs font-bold text-gray-500 uppercase">Disabled</p>
        <p class="text-2xl font-black text-gray-400">{{ status.disabled }}</p>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <p class="text-xs font-bold text-gray-500 uppercase">Core</p>
        <p class="text-2xl font-black text-kivotos-pink">{{ status.core }}</p>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <p class="text-xs font-bold text-gray-500 uppercase">Builtin</p>
        <p class="text-2xl font-black text-kivotos-cyan">{{ builtinTools.length }}</p>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <p class="text-xs font-bold text-gray-500 uppercase">MCP</p>
        <p class="text-2xl font-black text-purple-600">{{ mcpTools.length }}</p>
      </div>
    </div>

    <!-- Filter -->
    <div class="flex gap-2 flex-wrap">
      <button
        v-for="f in ['all', 'enabled', 'disabled', ...categories]"
        :key="f"
        @click="filter = f"
        class="px-3 py-1.5 rounded-lg text-sm font-bold transition-colors"
        :class="filter === f
          ? 'bg-kivotos-cyan text-white'
          : 'bg-white text-gray-600 hover:bg-gray-50 border border-gray-200'"
      >
        {{ f === 'all' ? 'All' : categoryLabels[f] || f.charAt(0).toUpperCase() + f.slice(1) }}
      </button>
    </div>

    <!-- Tools List -->
    <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden flex-1">
      <div class="divide-y divide-gray-100 max-h-[500px] overflow-y-auto">
        <div
          v-for="tool in filteredTools"
          :key="tool.name"
          class="p-4 hover:bg-slate-50 transition-colors"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <Wrench v-if="tool.source === 'builtin'" :size="16" class="text-kivotos-cyan flex-shrink-0" />
                <Server v-else :size="16" class="text-purple-500 flex-shrink-0" />
                <span class="font-bold text-kivotos-navy">{{ tool.name }}</span>
                <span
                  v-if="tool.is_core"
                  class="px-1.5 py-0.5 bg-kivotos-pink/10 text-kivotos-pink text-xs font-bold rounded flex items-center gap-1"
                >
                  <Shield :size="10" /> Core
                </span>
                <span
                  v-if="tool.source === 'mcp'"
                  class="px-1.5 py-0.5 bg-purple-100 text-purple-700 text-xs font-bold rounded flex items-center gap-1"
                >
                  <Server :size="10" /> {{ tool.source_name }}
                </span>
                <span
                  class="px-1.5 py-0.5 text-xs font-bold rounded"
                  :class="tool.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                >
                  {{ tool.enabled ? 'ON' : 'OFF' }}
                </span>
              </div>
              <p class="text-sm text-gray-600 mb-2">{{ tool.description }}</p>
              <div class="flex items-center gap-2 flex-wrap">
                <span class="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded font-mono">
                  {{ tool.category }}
                </span>
                <span
                  v-for="tag in tool.tags"
                  :key="tag"
                  class="px-2 py-0.5 bg-kivotos-cyan/10 text-kivotos-cyan text-xs rounded"
                >
                  {{ tag }}
                </span>
              </div>
            </div>
            <button
              @click="toggleTool(tool)"
              :disabled="tool.is_core"
              class="p-2 rounded-lg transition-colors"
              :class="tool.is_core
                ? 'text-gray-300 cursor-not-allowed'
                : tool.enabled
                  ? 'text-green-500 hover:bg-green-50'
                  : 'text-gray-400 hover:bg-gray-100'"
              :title="tool.is_core ? 'Core tools cannot be disabled' : (tool.enabled ? 'Disable' : 'Enable')"
            >
              <ToggleRight v-if="tool.enabled" :size="24" />
              <ToggleLeft v-else :size="24" />
            </button>
          </div>
        </div>

        <div v-if="filteredTools.length === 0" class="p-8 text-center text-gray-400">
          <Wrench :size="32" class="mx-auto mb-2 opacity-50" />
          <p>No tools found</p>
        </div>
      </div>
    </div>
  </div>
</template>

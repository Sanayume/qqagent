<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

interface LogEntry {
  time: string
  level: string
  message: string
  module: string
  line: number
  timestamp: number
}

const authStore = useAuthStore()
const logs = ref<LogEntry[]>([])
const isConnected = ref(false)
const autoScroll = ref(true)
const searchQuery = ref('')
const selectedLevel = ref('ALL')
const logContainer = ref<HTMLElement | null>(null)
let ws: WebSocket | null = null

const LEVELS = ['ALL', 'DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL']

function getLevelColor(level: string) {
  switch (level.toUpperCase()) {
    case 'DEBUG': return 'text-gray-400 bg-gray-500/10'
    case 'INFO': return 'text-miku-400 bg-miku-500/10'
    case 'SUCCESS': return 'text-green-400 bg-green-500/10'
    case 'WARNING': return 'text-yellow-400 bg-yellow-500/10'
    case 'ERROR': return 'text-red-400 bg-red-500/10'
    case 'CRITICAL': return 'text-red-500 font-bold bg-red-500/20'
    default: return 'text-gray-300 bg-gray-500/10'
  }
}

const filteredLogs = computed(() => {
  let result = logs.value
  if (selectedLevel.value !== 'ALL') {
    result = result.filter(log => log.level.toUpperCase() === selectedLevel.value)
  }
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(log => 
      log.message.toLowerCase().includes(query) ||
      log.module.toLowerCase().includes(query)
    )
  }
  return result
})

const levelCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const level of LEVELS) {
    if (level === 'ALL') {
      counts[level] = logs.value.length
    } else {
      counts[level] = logs.value.filter(l => l.level.toUpperCase() === level).length
    }
  }
  return counts
})

function connect() {
  const url = `ws://localhost:8088/api/logs/stream?token=${authStore.token}`
  console.log('Connecting to:', url)
  
  ws = new WebSocket(url)
  
  ws.onopen = () => {
    isConnected.value = true
    console.log('WebSocket connected')
  }
  
  ws.onerror = (e) => {
    console.error('WebSocket error:', e)
  }
  
  ws.onclose = () => {
    isConnected.value = false
    setTimeout(connect, 3000)
  }
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      logs.value.push(data)
      if (logs.value.length > 2000) {
        logs.value = logs.value.slice(-1000)
      }
      if (autoScroll.value) {
        scrollToBottom()
      }
    } catch (e) {
      console.error('Failed to parse log:', e)
    }
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

function clearLogs() {
  logs.value = []
}

function toggleAutoScroll() {
  autoScroll.value = !autoScroll.value
  if (autoScroll.value) {
    scrollToBottom()
  }
}

async function generateTestLogs() {
  try {
    await api.post('/api/logs/test')
  } catch (e) {
    console.error('Failed to generate test logs:', e)
  }
}

onMounted(() => {
  connect()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
})
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- 顶部工具栏 -->
    <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
      <div class="flex items-center gap-4">
        <h1 class="text-2xl font-bold text-white">实时日志</h1>
        <div class="flex items-center gap-2 px-3 py-1 rounded-full bg-night-950 border border-gray-800">
          <div 
            class="w-2 h-2 rounded-full transition-colors duration-300"
            :class="isConnected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-red-500 animate-pulse'"
          ></div>
          <span class="text-xs text-gray-400">{{ isConnected ? '已连接' : '连接中...' }}</span>
        </div>
      </div>
      
      <div class="flex items-center gap-3 flex-wrap">
        <!-- 级别过滤 -->
        <div class="flex gap-1 bg-night-950 p-1 rounded-lg border border-gray-800">
          <button 
            v-for="level in LEVELS" 
            :key="level"
            @click="selectedLevel = level"
            class="px-2 py-1 text-xs rounded transition-all"
            :class="selectedLevel === level 
              ? 'bg-white/10 text-white font-bold' 
              : 'text-gray-500 hover:text-gray-300'"
          >
            {{ level }}
            <span v-if="levelCounts[level] > 0" class="ml-1 opacity-60">({{ levelCounts[level] }})</span>
          </button>
        </div>
        
        <!-- 搜索框 -->
        <input 
          v-model="searchQuery"
          type="text" 
          placeholder="🔍 搜索..." 
          class="w-40 bg-night-950 border border-gray-700 text-gray-200 text-sm rounded-lg px-3 py-1.5 focus:border-miku-500 focus:outline-none transition-all placeholder-gray-600"
        >
        
        <button 
          @click="toggleAutoScroll"
          class="px-3 py-1.5 rounded-lg border text-xs transition-all"
          :class="autoScroll 
            ? 'bg-miku-500/10 border-miku-500/30 text-miku-400' 
            : 'bg-night-950 border-gray-700 text-gray-400'"
        >
          📜 {{ autoScroll ? 'ON' : 'OFF' }}
        </button>
        
        <button 
          @click="generateTestLogs"
          class="px-3 py-1.5 rounded-lg bg-sakura-500/10 border border-sakura-500/30 text-sakura-400 text-xs hover:bg-sakura-500/20 transition-all"
        >
          🧪 测试
        </button>
        
        <button 
          @click="clearLogs"
          class="px-3 py-1.5 rounded-lg bg-night-950 border border-gray-700 text-gray-400 text-xs hover:text-red-400 hover:border-red-500/30 transition-all"
        >
          🗑️
        </button>
      </div>
    </div>

    <!-- 日志显示区 -->
    <div 
      ref="logContainer"
      class="flex-1 bg-night-950/80 backdrop-blur rounded-xl border border-sakura-500/10 overflow-y-auto p-4 font-mono text-xs shadow-inner custom-scrollbar"
    >
      <div v-if="!isConnected" class="h-full flex flex-col items-center justify-center text-gray-600">
        <div class="w-8 h-8 border-2 border-miku-500/30 border-t-miku-500 rounded-full animate-spin mb-4"></div>
        <p>正在连接日志服务...</p>
      </div>
      
      <div v-else-if="filteredLogs.length === 0" class="h-full flex flex-col items-center justify-center text-gray-600">
        <div class="text-4xl mb-4 opacity-20">📝</div>
        <p>暂无日志数据</p>
        <button @click="generateTestLogs" class="mt-4 px-4 py-2 bg-sakura-500/20 text-sakura-400 rounded-lg text-sm hover:bg-sakura-500/30 transition-colors">
          点击生成测试日志
        </button>
      </div>
      
      <div v-else class="space-y-0.5">
        <div 
          v-for="(log, index) in filteredLogs" 
          :key="index"
          class="group hover:bg-white/5 px-2 py-1 rounded transition-colors flex items-start gap-2"
        >
          <span class="text-gray-600 shrink-0 select-none w-16">{{ log.time?.split(' ')[1] || '--:--:--' }}</span>
          <span 
            class="shrink-0 w-16 text-center text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider"
            :class="getLevelColor(log.level)"
          >
            {{ log.level }}
          </span>
          <span class="text-gray-600 shrink-0 w-20 truncate text-right" :title="log.module">
            {{ log.module?.split('.').pop() || 'unknown' }}
          </span>
          <span class="text-gray-300 group-hover:text-white transition-colors break-all">{{ log.message }}</span>
        </div>
      </div>
    </div>
    
    <!-- 底部状态栏 -->
    <div class="mt-2 flex items-center justify-between text-xs text-gray-600">
      <span>共 {{ logs.length }} 条，显示 {{ filteredLogs.length }} 条</span>
      <span>💡 点击 "🧪 测试" 按钮生成日志验证连接</span>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 3px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>

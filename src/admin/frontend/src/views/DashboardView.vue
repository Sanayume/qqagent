<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import {
  Activity,
  Server,
  Clock,
  Terminal,
  Zap,
  Radio,
  List
} from 'lucide-vue-next'

const router = useRouter()
const systemStatus = ref({
  agent: {
    status: 'stopped',
    uptime: 'N/A',
    model: null,
    session_count: 0,
    messages_processed: 0
  },
  mcp: {
    count: 0,
    servers: []
  },
  presets: {
    count: 0,
    current: 'None'
  }
})

const logs = ref<string[]>([])
let logWs: WebSocket | null = null

function connectLogStream() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}/api/logs/stream`

  logWs = new WebSocket(url)
  logWs.onmessage = (event) => {
    const log = event.data
    logs.value.unshift(log)
    if (logs.value.length > 20) logs.value.pop()
  }
}

async function fetchStatus() {
  try {
    const res = await axios.get('/api/status')
    systemStatus.value = res.data
  } catch (e) {
    console.error("Failed to fetch status", e)
  }
}

let statusInterval: any
onMounted(() => {
  fetchStatus()
  connectLogStream()
  statusInterval = setInterval(fetchStatus, 5000)
})

onUnmounted(() => {
  if (logWs) logWs.close()
  clearInterval(statusInterval)
})
</script>

<template>
  <div class="h-full flex flex-col gap-6">
    
    <!-- Welcome Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-3xl font-black text-kivotos-navy tracking-tight skew-x-[-5deg] uppercase">
          System Overview
        </h2>
        <p class="text-kivotos-gray font-mono text-xs mt-1 font-bold">CONTROL PANEL // ONLINE</p>
      </div>
      <div class="flex items-center gap-2 bg-white px-4 py-2 rounded-lg border border-kivotos-cyan shadow-sm">
        <Clock class="text-kivotos-cyan" :size="16" />
        <span class="font-mono font-bold text-kivotos-navy">{{ new Date().toLocaleTimeString() }}</span>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
      
      <!-- Left Column: Status Modules -->
      <div class="space-y-6 lg:col-span-2 flex flex-col gap-6">
        
        <!-- Quick Stats Row -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <!-- Stat Card 1 -->
          <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm relative overflow-hidden group hover:border-kivotos-cyan transition-colors">
            <div class="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
              <Zap :size="48" class="text-kivotos-cyan" />
            </div>
            <p class="text-xs font-bold text-gray-500 uppercase tracking-wider">Agent Status</p>
            <div class="flex items-center gap-2 mt-2">
              <span class="w-3 h-3 rounded-full" :class="systemStatus.agent?.status === 'running' ? 'bg-green-500 animate-pulse' : 'bg-gray-300'"></span>
              <span class="text-xl font-black text-kivotos-navy">
                {{ systemStatus.agent?.status === 'running' ? 'ACTIVE' : 'STANDBY' }}
              </span>
            </div>
          </div>

           <!-- Stat Card 2 -->
           <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm relative overflow-hidden group hover:border-kivotos-pink transition-colors">
            <div class="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
              <Server :size="48" class="text-kivotos-pink" />
            </div>
            <p class="text-xs font-bold text-gray-500 uppercase tracking-wider">MCP Servers</p>
            <div class="flex items-center gap-2 mt-2">
              <span class="text-xl font-black text-kivotos-navy">{{ systemStatus.mcp?.count || 0 }}</span>
              <span class="text-xs px-1.5 py-0.5 bg-kivotos-pink/10 text-kivotos-pink rounded font-bold">ONLINE</span>
            </div>
          </div>

          <!-- Stat Card 3 -->
           <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm relative overflow-hidden group hover:border-kivotos-blue transition-colors">
            <div class="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
              <List :size="48" class="text-kivotos-blue" />
            </div>
            <p class="text-xs font-bold text-gray-500 uppercase tracking-wider">Active Preset</p>
            <div class="mt-2 text-lg font-bold text-kivotos-navy truncate" :title="systemStatus.presets?.current">
              {{ systemStatus.presets?.current || 'None' }}
            </div>
          </div>

          <!-- Stat Card 4 -->
           <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm relative overflow-hidden group hover:border-kivotos-yellow transition-colors">
            <div class="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
              <Activity :size="48" class="text-kivotos-yellow" />
            </div>
            <p class="text-xs font-bold text-gray-500 uppercase tracking-wider">Uptime</p>
            <div class="mt-2 text-xl font-black text-kivotos-navy font-mono">
              {{ systemStatus.agent?.uptime || 'N/A' }}
            </div>
          </div>
        </div>

        <!-- System Illustration / Banner -->
        <div class="bg-gradient-to-r from-kivotos-cyan to-kivotos-blue rounded-2xl p-6 text-white relative overflow-hidden shadow-lg shadow-kivotos-cyan/20 flex-1 min-h-[200px] flex items-center">
          <div class="absolute inset-0 bg-[url('/bg-pattern.svg')] opacity-10"></div>
          
          <!-- Decorative Circles -->
          <div class="absolute -right-10 -bottom-10 w-48 h-48 bg-white/10 rounded-full blur-2xl"></div>
          <div class="absolute top-10 right-20 w-20 h-20 bg-kivotos-pink/20 rounded-full blur-xl"></div>

          <div class="relative z-10 max-w-lg">
            <div class="flex items-center gap-2 mb-2 opacity-80">
              <Radio class="animate-pulse" />
              <span class="text-xs font-mono tracking-widest uppercase font-bold">System Notification</span>
            </div>
            <h3 class="text-3xl font-black italic mb-4">
              All Systems Operational
            </h3>
            <p class="text-white/90 text-sm leading-relaxed mb-6 font-medium">
              The Agent is currently running within normal parameters. 
              Efficiency is nominal.
            </p>
            <div class="flex gap-3">
              <button @click="router.push('/sandbox')" class="bg-white text-kivotos-blue px-5 py-2 rounded-lg font-bold hover:bg-blue-50 transition-colors shadow-sm text-sm border-2 border-transparent">
                Open Sandbox
              </button>
              <button @click="router.push('/logs')" class="bg-kivotos-navy/40 text-white px-5 py-2 rounded-lg font-bold hover:bg-kivotos-navy/50 transition-colors backdrop-blur-sm text-sm border border-white/30">
                View Logs
              </button>
            </div>
          </div>
        </div>

      </div>

      <!-- Right Column: Terminal -->
      <div class="bg-kivotos-navy rounded-2xl p-1 shadow-xl flex flex-col h-full overflow-hidden border border-kivotos-navy">
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
          <div v-for="(log, index) in logs" :key="index" class="mb-2 break-all border-l-2 pl-2 border-white/10 hover:border-kivotos-cyan/50 transition-colors group">
            <span class="text-kivotos-gray block mb-0.5 text-[10px]">{{ new Date().toLocaleTimeString() }}</span>
            <span class="text-gray-300 group-hover:text-white transition-colors leading-relaxed">{{ log }}</span>
          </div>
          <div v-if="logs.length === 0" class="text-gray-600 italic text-center mt-10">
            Waiting for data stream...
          </div>
        </div>
      </div>
    
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

interface MCPServer {
  command: string
  args: string[]
  env: Record<string, string>
}

interface ServerItem {
  name: string
  config: MCPServer
  status: string
}

const servers = ref<ServerItem[]>([])
const loading = ref(false)
const showModal = ref(false)
const isEditing = ref(false)

const form = ref({
  name: '',
  command: '',
  args: '',
  env: ''
})

async function fetchServers() {
  loading.value = true
  try {
    const res = await api.get('/api/mcp/servers')
    servers.value = Object.entries(res.data).map(([name, config]) => ({
      name,
      config: config as MCPServer,
      status: 'configured'
    }))
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function openAddModal() {
  isEditing.value = false
  form.value = { name: '', command: '', args: '', env: '{}' }
  showModal.value = true
}

function openEditModal(item: ServerItem) {
  isEditing.value = true
  form.value = {
    name: item.name,
    command: item.config.command,
    args: JSON.stringify(item.config.args),
    env: JSON.stringify(item.config.env, null, 2)
  }
  showModal.value = true
}

async function handleSubmit() {
  try {
    let argsArray = []
    try {
      if (form.value.args.trim()) {
        argsArray = JSON.parse(form.value.args)
      } else {
         // 尝试简单的空格分割，如果不是 JSON
         // 但为了安全，我们强制要求 JSON 数组格式，或者空
         argsArray = []
      }
    } catch {
       alert('Args 必须是有效的 JSON 数组')
       return
    }

    let envObj = {}
    try {
      envObj = JSON.parse(form.value.env || '{}')
    } catch {
      alert('Env 必须是有效的 JSON 对象')
      return
    }

    const payload = {
      command: form.value.command,
      args: argsArray,
      env: envObj
    }

    if (isEditing.value) {
      await api.put(`/api/mcp/servers/${form.value.name}`, payload)
    } else {
      await api.post('/api/mcp/servers', {
        name: form.value.name,
        config: payload
      })
    }
    
    showModal.value = false
    fetchServers()
    
  } catch (e: any) {
    alert(e.response?.data?.detail || '操作失败')
  }
}

async function handleDelete(name: string) {
  if (!confirm(`确定要删除 ${name} 吗？`)) return
  try {
    await api.delete(`/api/mcp/servers/${name}`)
    fetchServers()
  } catch (e) {
    console.error(e)
  }
}

onMounted(fetchServers)
</script>

<template>
  <div class="h-full flex flex-col p-6">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-3xl font-bold text-white mb-2">MCP 服务器管理</h1>
        <p class="text-gray-400">管理 Model Context Protocol 服务器配置</p>
      </div>
      <button 
        @click="openAddModal"
        class="px-6 py-3 bg-gradient-to-r from-miku-500 to-miku-600 text-white rounded-xl font-bold hover:shadow-lg hover:shadow-miku-500/20 active:scale-95 transition-all flex items-center gap-2"
      >
        <span>➕</span> 添加服务器
      </button>
    </div>

    <!-- 服务器卡片列表 -->
    <div v-if="loading" class="text-center py-20 text-gray-500">加载中...</div>
    
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div 
        v-for="server in servers" 
        :key="server.name"
        class="bg-night-900/50 backdrop-blur border border-sakura-500/10 rounded-2xl p-6 hover:border-sakura-500/30 transition-all group relative overflow-hidden"
      >
        <!-- 背景装饰 -->
        <div class="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-miku-500/10 to-transparent rounded-bl-3xl -z-10 group-hover:from-miku-500/20 transition-all"></div>

        <div class="flex items-start justify-between mb-4">
          <div class="flex items-center gap-3">
            <div class="w-12 h-12 bg-gray-800 rounded-xl flex items-center justify-center text-2xl border border-white/5">
              🔌
            </div>
            <div>
              <h3 class="text-xl font-bold text-white">{{ server.name }}</h3>
              <div class="flex items-center gap-2 mt-1">
                <span class="w-2 h-2 rounded-full bg-green-500"></span>
                <span class="text-xs text-gray-400">Configured</span>
              </div>
            </div>
          </div>
          
          <div class="flex gap-2 opacity-0 group-hover:opacity-100 transition-all">
            <button 
              @click="openEditModal(server)"
              class="p-2 hover:bg-white/10 rounded-lg text-gray-300 hover:text-white transition-colors" 
              title="编辑"
            >
              ✏️
            </button>
            <button 
              @click="handleDelete(server.name)"
              class="p-2 hover:bg-red-500/20 rounded-lg text-gray-300 hover:text-red-400 transition-colors"
              title="删除"
            >
              🗑️
            </button>
          </div>
        </div>

        <div class="space-y-3 text-sm text-gray-400 mb-4">
          <div class="flex gap-2">
            <span class="w-16 shrink-0 text-gray-500">Command:</span>
            <code class="text-miku-400 bg-miku-500/10 px-1 rounded">{{ server.config.command }}</code>
          </div>
          <div class="flex gap-2">
            <span class="w-16 shrink-0 text-gray-500">Args:</span>
            <span class="truncate">{{ server.config.args.join(' ') || '(none)' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 弹窗 -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="showModal = false"></div>
      
      <div class="relative w-full max-w-lg bg-night-900 border border-gray-700 rounded-2xl shadow-2xl p-6 animate-float">
        <h2 class="text-2xl font-bold text-white mb-6">{{ isEditing ? '编辑服务器' : '添加服务器' }}</h2>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Server Name</label>
            <input 
              v-model="form.name" 
              :disabled="isEditing"
              type="text" 
              class="w-full bg-night-950 border border-gray-700 rounded-xl px-4 py-2 text-white outline-none focus:border-sakura-500 transition-colors disabled:opacity-50"
            >
          </div>
          
          <div>
            <label class="block text-sm text-gray-400 mb-1">Command</label>
            <input 
              v-model="form.command" 
              type="text" 
              placeholder="e.g. npx, python, uvx"
              class="w-full bg-night-950 border border-gray-700 rounded-xl px-4 py-2 text-white outline-none focus:border-sakura-500 transition-colors"
            >
          </div>
          
          <div>
            <label class="block text-sm text-gray-400 mb-1">Args (JSON Array)</label>
            <textarea 
              v-model="form.args" 
              rows="3"
              placeholder='["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users"]'
              class="w-full bg-night-950 border border-gray-700 rounded-xl px-4 py-2 text-white outline-none focus:border-sakura-500 transition-colors font-mono text-sm"
            ></textarea>
          </div>
          
          <div>
            <label class="block text-sm text-gray-400 mb-1">Env (JSON Object)</label>
            <textarea 
              v-model="form.env" 
              rows="3"
              placeholder='{"KEY": "VALUE"}'
              class="w-full bg-night-950 border border-gray-700 rounded-xl px-4 py-2 text-white outline-none focus:border-sakura-500 transition-colors font-mono text-sm"
            ></textarea>
          </div>
        </div>
        
        <div class="flex gap-3 mt-8 justify-end">
          <button 
            @click="showModal = false"
            class="px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
          >
            取消
          </button>
          <button 
            @click="handleSubmit"
            class="px-6 py-2 bg-sakura-500 hover:bg-sakura-600 text-white rounded-lg font-bold transition-colors"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

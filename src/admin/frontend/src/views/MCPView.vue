<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import InlineNotice from '../components/InlineNotice.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import FormDialog from '../components/FormDialog.vue'

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
const saving = ref(false)
const deleting = ref(false)
const successMsg = ref('')
const errorMsg = ref('')
const formError = ref('')
const deleteTarget = ref<string | null>(null)

const form = ref({
  name: '',
  command: '',
  args: '',
  env: ''
})

async function fetchServers() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.get('/api/mcp/servers')
    servers.value = Object.entries(res.data).map(([name, config]) => ({
      name,
      config: config as MCPServer,
      status: 'configured'
    }))
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || '加载 MCP 服务器失败'
  } finally {
    loading.value = false
  }
}

function openAddModal() {
  isEditing.value = false
  form.value = { name: '', command: '', args: '', env: '{}' }
  formError.value = ''
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
  formError.value = ''
  showModal.value = true
}

async function handleSubmit() {
  formError.value = ''
  successMsg.value = ''
  errorMsg.value = ''
  const name = form.value.name.trim()
  const command = form.value.command.trim()
  if (!name && !isEditing.value) {
    formError.value = '请填写服务器名称'
    return
  }
  if (!command) {
    formError.value = '请填写 command'
    return
  }

  try {
    saving.value = true
    let argsArray = []
    try {
      if (form.value.args.trim()) {
        argsArray = JSON.parse(form.value.args)
      } else {
         argsArray = []
      }
      if (!Array.isArray(argsArray)) {
        formError.value = 'Args 必须是 JSON 数组'
        return
      }
    } catch {
      formError.value = 'Args 必须是有效的 JSON 数组'
      return
    }

    let envObj: Record<string, string> = {}
    try {
      envObj = JSON.parse(form.value.env || '{}')
      if (!envObj || typeof envObj !== 'object' || Array.isArray(envObj)) {
        formError.value = 'Env 必须是 JSON 对象'
        return
      }
    } catch {
      formError.value = 'Env 必须是有效的 JSON 对象'
      return
    }

    const payload = {
      command: form.value.command,
      args: argsArray,
      env: envObj
    }

    if (isEditing.value) {
      await api.put(`/api/mcp/servers/${form.value.name}`, payload)
      successMsg.value = `已更新服务器 ${form.value.name}`
    } else {
      await api.post('/api/mcp/servers', {
        name,
        config: payload
      })
      successMsg.value = `已添加服务器 ${name}`
    }

    showModal.value = false
    await fetchServers()
  } catch (e: any) {
    formError.value = e.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

function requestDelete(name: string) {
  deleteTarget.value = name
  errorMsg.value = ''
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    await api.delete(`/api/mcp/servers/${deleteTarget.value}`)
    successMsg.value = `已删除服务器 ${deleteTarget.value}`
    deleteTarget.value = null
    await fetchServers()
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || '删除失败'
  } finally {
    deleting.value = false
  }
}

onMounted(fetchServers)
</script>

<template>
  <div class="h-full flex flex-col p-6 gap-4">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-3xl font-black text-kivotos-navy mb-2">MCP 服务器管理</h1>
        <p class="text-kivotos-gray">管理 Model Context Protocol 服务器配置</p>
      </div>
      <button
        @click="openAddModal"
        class="px-6 py-3 bg-gradient-to-r from-miku-500 to-miku-600 text-white rounded-xl font-bold hover:shadow-lg hover:shadow-miku-500/20 active:scale-95 transition-all flex items-center gap-2"
      >
        <span>➕</span> 添加服务器
      </button>
    </div>

    <InlineNotice v-if="errorMsg" type="error" :message="errorMsg" @close="errorMsg = ''" />
    <InlineNotice v-if="successMsg" type="success" :message="successMsg" @close="successMsg = ''" />

    <!-- 服务器卡片列表 -->
    <div v-if="loading" class="text-center py-20 text-gray-500">加载中...</div>

    <div v-else-if="servers.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="server in servers"
        :key="server.name"
        class="bg-white border border-gray-200 rounded-2xl p-6 hover:border-kivotos-cyan/40 transition-all group relative overflow-hidden shadow-sm"
      >
        <!-- 背景装饰 -->
        <div class="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-miku-500/10 to-transparent rounded-bl-3xl -z-10 group-hover:from-miku-500/20 transition-all"></div>

        <div class="flex items-start justify-between mb-4">
          <div class="flex items-center gap-3">
            <div class="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center text-2xl border border-slate-200">
              🔌
            </div>
            <div>
              <h3 class="text-xl font-bold text-kivotos-navy">{{ server.name }}</h3>
              <div class="flex items-center gap-2 mt-1">
                <span class="w-2 h-2 rounded-full bg-green-500"></span>
                <span class="text-xs text-gray-500">Configured</span>
              </div>
            </div>
          </div>

          <div class="flex gap-2 opacity-0 group-hover:opacity-100 transition-all">
            <button
              @click="openEditModal(server)"
              class="p-2 hover:bg-slate-100 rounded-lg text-gray-500 hover:text-kivotos-navy transition-colors"
              title="编辑"
            >
              ✏️
            </button>
            <button
              @click="requestDelete(server.name)"
              class="p-2 hover:bg-red-100 rounded-lg text-gray-500 hover:text-red-500 transition-colors"
              title="删除"
            >
              🗑️
            </button>
          </div>
        </div>

        <div class="space-y-3 text-sm text-gray-600 mb-4">
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

    <div v-else class="flex-1 min-h-[220px] rounded-2xl border border-dashed border-gray-300 bg-white flex items-center justify-center">
      <div class="text-center">
        <p class="text-kivotos-navy font-bold mb-2">暂无 MCP 服务器</p>
        <p class="text-sm text-gray-500 mb-4">点击右上角“添加服务器”开始配置。</p>
        <button
          @click="openAddModal"
          class="px-4 py-2 rounded-lg bg-kivotos-navy text-white font-bold hover:bg-slate-800"
        >
          添加服务器
        </button>
      </div>
    </div>

    <FormDialog
      :open="showModal"
      :title="isEditing ? '编辑服务器' : '添加服务器'"
      confirm-text="保存"
      cancel-text="取消"
      :loading="saving"
      @close="showModal = false"
      @confirm="handleSubmit"
    >
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
      <div v-if="formError" class="mt-4 rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
        {{ formError }}
      </div>
    </FormDialog>

    <ConfirmDialog
      :open="Boolean(deleteTarget)"
      title="确认删除"
      :message="deleteTarget ? `确定要删除服务器 ${deleteTarget} 吗？` : ''"
      confirm-text="删除"
      cancel-text="取消"
      :loading="deleting"
      danger
      @close="deleteTarget = null"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

// ==================== Types ====================
interface User {
  qq: number
  nickname: string
  avatar: string
  is_bot: boolean
}

interface Group {
  group_id: number
  name: string
  members: number[]
}

interface Message {
  message_id: number
  sender_qq: number
  content: string
  image: string
  timestamp: string
  chat_type: 'group' | 'private'
  group_id: number | null
  target_qq: number | null
  sender?: User
  reply_to?: number
  at_users?: number[]
}

// ==================== State ====================
const authStore = useAuthStore()
const users = ref<User[]>([])
const groups = ref<Group[]>([])
const messages = ref<Message[]>([])
const isConnected = ref(false)
let ws: WebSocket | null = null

// UI State
const currentUserQQ = ref<number>(10001) // 默认选中的发送者
const currentChatType = ref<'group' | 'private'>('group')
const currentChatId = ref<number>(100001) // 当前群ID或对方QQ
const inputText = ref('')
const chateArea = ref<HTMLElement | null>(null)
const sending = ref(false)

// ... (methods) ...

function getUser(qq: number) {
    return users.value.find(u => u.qq === qq)
}

// ==================== Computed ====================
const currentChatName = computed(() => {
  if (currentChatType.value === 'group') {
    const g = groups.value.find(g => g.group_id === currentChatId.value)
    return g ? g.name : `群 ${currentChatId.value}`
  } else {
    const u = users.value.find(u => u.qq === currentChatId.value)
    return u ? u.nickname : `用户 ${currentChatId.value}`
  }
})

const currentMessages = computed(() => {
  return messages.value.filter(msg => {
    if (msg.chat_type !== currentChatType.value) return false
    if (msg.chat_type === 'group') {
      return msg.group_id === currentChatId.value
    } else {
      // 私聊：只显示当前模拟用户发给 bot(或其他) 的，或者 bot 发给当前模拟用户的
      // 但这里我们是上帝视角，显示该会话的所有消息
      // 即：涉及 currentChatId (作为对方) 且 涉及 currentUserQQ (作为本人) ?
      // 不，沙盒通常有一个主视角的概念。
      // 这里简化：左侧选择“会话”，比如 "与 Bot 的私聊"
      
      // 现在的逻辑：currentChatId 是对方ID。
      // 如果聊天类型是私聊，我们显示 sender=currentChatId OR target=currentChatId 的消息
      // 但这会混杂和其他人的私聊。
      
      // 让我们简化模型：左侧列出 "群组" 和 "用户"
      // 点击群组 -> 显示群消息
      // 点击用户 -> 显示该用户的所有私聊（主要是和 Bot 的）
      return (msg.sender_qq === currentChatId.value || msg.target_qq === currentChatId.value)
    }
  })
})

// ==================== Methods ====================

async function fetchState() {
  const res = await api.get('/api/sandbox/state')
  users.value = res.data.users
  groups.value = res.data.groups
  messages.value = res.data.messages
  
  // 确保有默认选中
  if (!currentUserQQ.value && users.value.length > 0) {
    const nonBot = users.value.find(u => !u.is_bot)
    const first = users.value[0]
    currentUserQQ.value = nonBot?.qq ?? first?.qq ?? 0
  }
}

function connectWS() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = import.meta.env.VITE_API_URL 
    ? import.meta.env.VITE_API_URL.replace(/^http/, 'ws') 
    : `${protocol}//${window.location.host.replace(/:\d+$/, ':8088')}` 
    
  const url = `${host}/api/sandbox/ws?token=${authStore.token}`
  ws = new WebSocket(url)
  
  ws.onopen = () => isConnected.value = true
  ws.onclose = () => {
    isConnected.value = false
    setTimeout(connectWS, 3000)
  }
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'new_message') {
      messages.value.push(data.data)
      scrollToBottom()
    } else if (data.type === 'user_update') {
      const idx = users.value.findIndex(u => u.qq === data.data.qq)
      if (idx !== -1) users.value[idx] = data.data
      else users.value.push(data.data)
    } else if (data.type === 'group_update') {
      const idx = groups.value.findIndex(g => g.group_id === data.data.group_id)
      if (idx !== -1) groups.value[idx] = data.data
      else groups.value.push(data.data)
    }
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (chateArea.value) {
      chateArea.value.scrollTop = chateArea.value.scrollHeight
    }
  })
}

async function sendMessage() {
  if (!inputText.value.trim() || sending.value) return
  
  sending.value = true
  try {
    await api.post('/api/sandbox/send', {
      sender_qq: currentUserQQ.value,
      content: inputText.value,
      chat_type: currentChatType.value,
      group_id: currentChatType.value === 'group' ? currentChatId.value : null,
      target_qq: currentChatType.value === 'private' ? currentChatId.value : null,
    })
    inputText.value = ''
    scrollToBottom()
  } catch (e) {
    console.error(e)
    alert('发送失败')
  } finally {
    sending.value = false
  }
}

// 辅助方法
function getAvatar(qq: number) {
  const u = users.value.find(u => u.qq === qq)
  return u?.avatar || `https://q1.qlogo.cn/g?b=qq&nk=${qq}&s=100`
}

function getNickname(qq: number) {
  const u = users.value.find(u => u.qq === qq)
  return u?.nickname || `${qq}`
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString()
}

onMounted(() => {
  fetchState().then(scrollToBottom)
  connectWS()
})

onUnmounted(() => {
  if (ws) ws.close()
})
</script>

<template>
  <div class="h-full flex gap-4 overflow-hidden">
    <!-- 左侧：会话列表 -->
    <div class="w-64 flex flex-col gap-4 bg-night-900/50 backdrop-blur rounded-2xl border border-sakura-500/10 p-4">
      <h2 class="text-white font-bold opacity-80">会话列表</h2>
      
      <!-- 群组列表 -->
      <div class="space-y-1">
        <div class="text-xs text-gray-500 font-bold mb-1 ml-2">群聊</div>
        <div 
          v-for="group in groups" 
          :key="group.group_id"
          class="flex items-center gap-3 p-2 rounded-xl cursor-pointer transition-all hover:bg-white/5"
          :class="currentChatType === 'group' && currentChatId === group.group_id ? 'bg-sakura-500/20 text-white' : 'text-gray-400'"
          @click="currentChatType = 'group'; currentChatId = group.group_id; scrollToBottom()"
        >
          <div class="w-10 h-10 bg-sakura-500/20 rounded-full flex items-center justify-center text-lg">
            👥
          </div>
          <div class="truncate">{{ group.name }}</div>
        </div>
      </div>

      <!-- 用户列表 (私聊对象) -->
      <div class="space-y-1 flex-1 overflow-y-auto custom-scrollbar">
        <div class="text-xs text-gray-500 font-bold mb-1 ml-2">私聊 (Bot)</div>
        <div 
          v-for="user in users.filter(u => u.is_bot)" 
          :key="user.qq"
          class="flex items-center gap-3 p-2 rounded-xl cursor-pointer transition-all hover:bg-white/5"
          :class="currentChatType === 'private' && currentChatId === user.qq ? 'bg-miku-500/20 text-white' : 'text-gray-400'"
          @click="currentChatType = 'private'; currentChatId = user.qq; scrollToBottom()"
        >
          <img :src="user.avatar" class="w-10 h-10 rounded-full border border-miku-500/30">
          <div class="truncate">{{ user.nickname }}</div>
        </div>
      </div>
    </div>

    <!-- 中间：聊天区域 -->
    <div class="flex-1 flex flex-col bg-night-900/50 backdrop-blur rounded-2xl border border-sakura-500/10 overflow-hidden relative">
      <!-- 头部 -->
      <div class="p-4 border-b border-white/5 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span class="text-xl font-bold text-white">{{ currentChatName }}</span>
          <span class="text-xs px-2 py-0.5 rounded-full bg-miku-500/20 text-miku-400">
            {{ currentChatType === 'group' ? 'Group' : 'Private' }}
          </span>
        </div>
        <div class="text-xs text-gray-500">
          {{ isConnected ? '✅ 实时连接' : '❌ 连接断开' }}
        </div>
      </div>

      <!-- 消息列表 -->
      <div ref="chateArea" class="flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar scroll-smooth">
        <div 
          v-for="msg in currentMessages" 
          :key="msg.message_id"
          class="flex gap-4 group"
          :class="msg.sender_qq === currentUserQQ ? 'flex-row-reverse' : ''"
        >
          <!-- 头像 -->
          <img 
            :src="getAvatar(msg.sender_qq)" 
            class="w-10 h-10 rounded-full border-2 border-night-800 shadow-md shrink-0 mt-1 cursor-pointer hover:border-sakura-500 transition-colors"
            title="点击切换为此用户"
            @click="currentUserQQ = msg.sender_qq"
          >
          
          <!-- 消息内容 -->
          <div class="flex flex-col gap-1 max-w-[70%]" :class="msg.sender_qq === currentUserQQ ? 'items-end' : 'items-start'">
            <div class="flex items-center gap-2 text-xs text-gray-500 px-1">
              <span>{{ getNickname(msg.sender_qq) }}</span>
              <span>{{ formatTime(msg.timestamp) }}</span>
            </div>
            
            <div 
              class="px-4 py-2.5 rounded-2xl shadow-sm text-sm break-words leading-relaxed relative"
              :class="[
                msg.sender_qq === currentUserQQ 
                  ? 'bg-gradient-to-br from-sakura-500 to-sakura-600 text-white rounded-tr-sm' 
                  : 'bg-white/10 text-gray-200 rounded-tl-sm border border-white/5'
              ]"
            >
              <!-- 引用 -->
              <div v-if="msg.reply_to" class="mb-2 px-2 py-1 bg-black/20 rounded border-l-2 border-white/30 text-xs opacity-80 truncate max-w-xs">
                回复消息 #{{ msg.reply_to }}
              </div>
              
              <!-- @ -->
              <div v-if="msg.at_users?.length" class="mb-1 text-miku-300 text-xs font-bold">
                @{{ msg.at_users.map(getNickname).join(' @') }}
              </div>

              {{ msg.content }}
              
              <div v-if="msg.image" class="mt-2">
                <img :src="msg.image" class="max-w-full rounded-lg border border-white/10">
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部输入栏 -->
      <div class="p-4 bg-night-950/50 border-t border-white/5">
        <div class="flex items-center gap-3 mb-3">
          <span class="text-xs text-gray-500">模拟身份:</span>
          <select 
            v-model="currentUserQQ" 
            class="bg-night-900 border border-gray-700 text-white text-xs rounded-lg px-2 py-1 focus:border-sakura-500 outline-none"
          >
            <option v-for="u in users" :key="u.qq" :value="u.qq">
              {{ u.nickname }} ({{ u.qq }})
            </option>
          </select>
        </div>
        
        <div class="flex gap-3">
          <textarea
            v-model="inputText"
            @keydown.enter.ctrl.exact="sendMessage"
            placeholder="输入消息... (Ctrl+Enter 发送)"
            class="flex-1 bg-night-900 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:border-sakura-500 focus:ring-1 focus:ring-sakura-500 outline-none resize-none h-24 custom-scrollbar"
          ></textarea>
          
          <button 
            @click="sendMessage"
            :disabled="sending || !inputText.trim()"
            class="px-6 rounded-xl bg-gradient-to-br from-miku-500 to-miku-600 text-white font-bold hover:shadow-lg hover:shadow-miku-500/20 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex flex-col items-center justify-center gap-1 w-24"
          >
            <span class="text-xl">🚀</span>
            <span class="text-xs">发送</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 右侧：控制面板 -->
    <div class="w-64 flex flex-col gap-4">
      <!-- 快速操作 -->
      <div class="bg-night-900/50 backdrop-blur rounded-2xl border border-sakura-500/10 p-4">
        <h2 class="text-white font-bold opacity-80 mb-4">操作</h2>
        <div class="grid grid-cols-2 gap-2">
          <button class="p-2 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-gray-300 border border-white/5 transition-colors">
            ➕ 添加用户
          </button>
          <button class="p-2 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-gray-300 border border-white/5 transition-colors">
            ➕ 创建群组
          </button>
          <button class="p-2 bg-red-500/10 hover:bg-red-500/20 rounded-lg text-xs text-red-400 border border-red-500/20 transition-colors col-span-2">
            🔄 重置数据
          </button>
        </div>
      </div>

      <!-- 成员列表 (当前群) -->
      <div class="flex-1 bg-night-900/50 backdrop-blur rounded-2xl border border-sakura-500/10 p-4 flex flex-col" v-if="currentChatType === 'group'">
        <h2 class="text-white font-bold opacity-80 mb-4 text-sm">群成员</h2>
        <div class="space-y-2 overflow-y-auto flex-1 custom-scrollbar">
          <div 
            v-for="qq in groups.find(g => g.group_id === currentChatId)?.members" 
            :key="qq"
            class="flex items-center gap-2 p-1.5 rounded-lg hover:bg-white/5 cursor-pointer group"
            @click="inputText += `@${qq} `"
          >
            <img :src="getAvatar(qq)" class="w-6 h-6 rounded-full">
            <span class="text-sm text-gray-400 group-hover:text-white truncate">{{ getNickname(qq) }}</span>
            <span v-if="getUser(qq)?.is_bot" class="text-[10px] bg-miku-500/20 text-miku-400 px-1 rounded">BOT</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 滚动条样式 */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.1);
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>

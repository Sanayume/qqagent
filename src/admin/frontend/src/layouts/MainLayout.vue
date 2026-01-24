<script setup lang="ts">
import { useAuthStore } from '../stores/auth'
import { useRouter, useRoute } from 'vue-router'
import {
  Home,
  ScrollText,
  MessageSquare,
  Server,
  FileJson,
  Settings,
  LogOut,
  User,
  Bot,
  Wrench
} from 'lucide-vue-next'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

const menuItems = [
  { path: '/', name: 'DASHBOARD', icon: Home },
  { path: '/agent', name: 'AGENT', icon: Bot },
  { path: '/tools', name: 'TOOLS', icon: Wrench },
  { path: '/logs', name: 'LOGS', icon: ScrollText },
  { path: '/sandbox', name: 'SANDBOX', icon: MessageSquare },
  { path: '/mcp', name: 'MCP', icon: Server },
  { path: '/presets', name: 'PRESETS', icon: FileJson },
  { path: '/config', name: 'CONFIG', icon: Settings },
]

const isActive = (path: string) => route.path === path
</script>

<template>
  <div class="min-h-screen flex flex-col font-display selection:bg-kivotos-cyan selection:text-white">
    
    <!-- Top Navigation Bar (Sticky with Skewed aesthetic) -->
    <header class="sticky top-0 z-50 h-16 bg-white/90 backdrop-blur-md border-b-[3px] border-kivotos-navy shadow-sm flex items-center justify-between px-6">
      
      <!-- Logo Area -->
      <div class="flex items-center gap-4">
        <div class="w-10 h-10 bg-kivotos-cyan flex items-center justify-center -skew-x-12 shadow-[4px_4px_0px_#0f172a]">
          <span class="text-2xl skew-x-12">🤖</span>
        </div>
        <div>
          <h1 class="font-black italic text-xl tracking-tighter text-kivotos-navy leading-none">
            QQ AGENT <span class="text-kivotos-cyan">CONSOLE</span>
          </h1>
          <p class="text-[10px] font-bold tracking-widest text-kivotos-gray uppercase">System Administration</p>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <nav class="hidden md:flex items-center gap-2">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="relative h-10 px-6 flex items-center justify-center transition-all duration-200 group skew-x-[-15deg] border-2 border-transparent hover:border-kivotos-cyan/30"
          :class="isActive(item.path) ? 'bg-kivotos-navy text-white shadow-[4px_4px_0px_#0ea5e9]' : 'bg-slate-100 text-slate-600 hover:bg-white hover:text-kivotos-navy'"
        >
          <div class="flex items-center gap-2 skew-x-[15deg]">
            <component :is="item.icon" :size="16" stroke-width="2.5" />
            <span class="font-bold text-sm tracking-wide">{{ item.name }}</span>
          </div>
          
          <!-- Active Indicator dot -->
           <div v-if="isActive(item.path)" class="absolute -top-1 -right-1 w-2 h-2 bg-kivotos-pink rounded-full border border-white"></div>
        </router-link>
      </nav>

      <!-- User Profile -->
      <div class="flex items-center gap-4">
        <div class="hidden md:flex flex-col items-end">
          <span class="font-bold text-sm text-kivotos-navy">Administrator</span>
          <span class="text-[10px] bg-kivotos-cyan/10 text-kivotos-cyan px-1 rounded font-mono font-bold">ROOT ACCESS</span>
        </div>
        
        <div class="w-10 h-10 rounded-full border-2 border-kivotos-navy bg-white flex items-center justify-center overflow-hidden cursor-pointer hover:ring-2 hover:ring-kivotos-pink transition-all shadow-sm">
          <User :size="20" class="text-kivotos-navy" />
        </div>

        <button 
          @click="handleLogout"
          class="p-2 text-slate-400 hover:text-kivotos-pink transition-colors"
          title="Logout"
        >
          <LogOut :size="20" />
        </button>
      </div>
    </header>

    <!-- Main Content Area with Geometric Decorations -->
    <main class="flex-1 relative p-6 overflow-hidden">
      <!-- Background Decorations -->
      <div class="fixed top-24 left-10 w-64 h-64 border-2 border-kivotos-gray/10 rounded-full pointer-events-none -z-10 dashed-circle"></div>
      <div class="fixed bottom-10 right-10 w-96 h-96 border-2 border-kivotos-cyan/5 rounded-full pointer-events-none -z-10"></div>
      
      <!-- Content Container -->
      <div class="max-w-7xl mx-auto h-full relative z-10">
        <router-view v-slot="{ Component }">
          <transition name="slide-up" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>

  </div>
</template>

<style scoped>
.dashed-circle {
  border-style: dashed;
  animation: spin 60s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-up-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.slide-up-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>


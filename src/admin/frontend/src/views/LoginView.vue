<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { Lock, User, ArrowRight, AlertCircle } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const showPassword = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) {
    error.value = 'Identity verification required.'
    return
  }

  loading.value = true
  error.value = ''

  try {
    await authStore.login(username.value, password.value)
    router.push('/')
  } catch (e: any) {
    error.value = 'Access Denied: Invalid credentials.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-6 relative overflow-hidden bg-kivotos-bg">
    
    <!-- Geometric Background Assets -->
    <div class="fixed inset-0 pointer-events-none">
      <div class="absolute top-0 right-0 w-1/2 h-full bg-white skew-x-[-20deg] translate-x-1/3 opacity-80"></div>
      <div class="absolute bottom-0 left-0 w-1/3 h-2/3 bg-kivotos-cyan/5 -skew-x-12 -translate-x-10"></div>
      
      <!-- Halo Rings -->
      <div class="absolute top-20 left-20 w-32 h-32 border-[3px] border-kivotos-pink/20 rounded-full animate-float"></div>
      <div class="absolute bottom-20 right-40 w-48 h-48 border-[2px] border-kivotos-blue/10 rounded-full animate-float" style="animation-delay: -2s"></div>
    </div>

    <!-- Login Container -->
    <div class="flex w-full max-w-4xl bg-white rounded-3xl overflow-hidden shadow-2xl relative z-10 animate-pop">
      
      <!-- Left: Visual Section (Hidden on Mobile) -->
      <div class="hidden md:flex w-1/2 bg-kivotos-navy relative flex-col justify-between p-12 text-white overflow-hidden">
        <div class="absolute inset-0 bg-gradient-to-br from-kivotos-cyan/20 to-transparent"></div>
        <div class="absolute -right-20 -bottom-20 w-64 h-64 bg-kivotos-pink/20 rounded-full blur-3xl"></div>
        
        <div class="relative z-10">
          <div class="w-16 h-16 bg-white rounded-2xl flex items-center justify-center text-3xl mb-8 shadow-lg text-kivotos-navy">
            🛡️
          </div>
          <h1 class="text-4xl font-black italic tracking-tighter leading-none mb-4">
            AGENT<br/>
            <span class="text-kivotos-cyan">CONSOLE</span>
          </h1>
          <p class="text-white/80 font-mono text-sm border-l-2 border-kivotos-cyan pl-4 font-medium">
            System Administration<br/>
            Authorized Access Only
          </p>
        </div>

        <div class="relative z-10 font-mono text-xs text-white/40">
          SECURE LOGIN // v2.0.0
        </div>
      </div>

      <!-- Right: Form Section -->
      <div class="w-full md:w-1/2 p-10 md:p-14 flex flex-col justify-center bg-white">
        
        <div class="mb-10">
          <h2 class="text-2xl font-bold text-kivotos-navy">Authentication</h2>
          <p class="text-kivotos-gray text-sm mt-1 font-medium">Please verify your identity</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-6">
          
          <!-- Username Input -->
          <div class="space-y-1">
            <label class="text-xs font-bold text-kivotos-navy uppercase tracking-widest pl-1">Username</label>
            <div class="relative group">
              <div class="absolute inset-y-0 left-4 flex items-center pointer-events-none text-kivotos-gray group-focus-within:text-kivotos-cyan transition-colors">
                <User :size="18" />
              </div>
              <input
                v-model="username"
                type="text"
                placeholder="Enter username"
                class="w-full pl-11 pr-4 py-3.5 bg-slate-50 border-2 border-slate-200 rounded-xl text-kivotos-navy placeholder-slate-400 focus:outline-none focus:border-kivotos-cyan focus:bg-white transition-all font-bold"
              />
            </div>
          </div>

          <!-- Password Input -->
          <div class="space-y-1">
            <label class="text-xs font-bold text-kivotos-navy uppercase tracking-widest pl-1">Password</label>
            <div class="relative group">
              <div class="absolute inset-y-0 left-4 flex items-center pointer-events-none text-kivotos-gray group-focus-within:text-kivotos-cyan transition-colors">
                <Lock :size="18" />
              </div>
              <input
                v-model="password"
                type="password"
                placeholder="••••••••"
                class="w-full pl-11 pr-4 py-3.5 bg-slate-50 border-2 border-slate-200 rounded-xl text-kivotos-navy placeholder-slate-400 focus:outline-none focus:border-kivotos-cyan focus:bg-white transition-all font-bold"
              />
            </div>
          </div>

          <!-- Error Alert -->
          <div v-if="error" class="flex items-center gap-2 p-3 bg-red-50 text-red-500 rounded-lg text-sm font-medium animate-slide-in">
            <AlertCircle :size="16" />
            <span>{{ error }}</span>
          </div>

          <!-- Submit Button -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-4 bg-kivotos-navy text-white rounded-xl font-bold text-sm uppercase tracking-widest hover:bg-kivotos-cyan hover:shadow-lg hover:shadow-kivotos-cyan/30 transition-all active:scale-[0.98] flex items-center justify-center gap-2 group disabled:opacity-70 disabled:cursor-not-allowed"
          >
            <span v-if="loading">Verifying...</span>
            <span v-else>Connect</span>
            <ArrowRight v-if="!loading" :size="16" class="group-hover:translate-x-1 transition-transform" />
          </button>
        </form>

        <div class="mt-8 pt-6 border-t border-gray-100 text-center">
          <p class="text-xs text-kivotos-gray">
            Default: <code class="bg-gray-100 px-1 py-0.5 rounded text-kivotos-navy font-bold">admin</code>
          </p>
        </div>
      </div>
    
    </div>
  </div>
</template>


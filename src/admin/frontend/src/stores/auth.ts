import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useAuthStore = defineStore('auth', () => {
    const token = ref<string | null>(localStorage.getItem('token'))
    const user = ref<{ username: string; display_name: string } | null>(null)

    const isAuthenticated = computed(() => !!token.value)

    async function login(username: string, password: string) {
        const response = await api.post('/api/auth/login', { username, password })
        token.value = response.data.access_token
        localStorage.setItem('token', response.data.access_token)
        await fetchUser()
    }

    async function fetchUser() {
        if (!token.value) return
        try {
            const response = await api.get('/api/auth/me')
            user.value = response.data
        } catch {
            logout()
        }
    }

    function logout() {
        token.value = null
        user.value = null
        localStorage.removeItem('token')
    }

    // 初始化时获取用户信息
    if (token.value) {
        fetchUser()
    }

    return {
        token,
        user,
        isAuthenticated,
        login,
        logout,
        fetchUser,
    }
})

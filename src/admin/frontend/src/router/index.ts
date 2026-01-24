import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
    {
        path: '/login',
        name: 'Login',
        component: () => import('../views/LoginView.vue'),
        meta: { requiresAuth: false }
    },
    {
        path: '/',
        name: 'Dashboard',
        component: () => import('../views/DashboardView.vue'),
        meta: { requiresAuth: true }
    },
    {
        path: '/agent',
        name: 'Agent',
        component: () => import('../views/AgentView.vue'),
        meta: { requiresAuth: true }
    },
    {
        path: '/logs',
        name: 'Logs',
        component: () => import('../views/LogsView.vue'),
        meta: { requiresAuth: true }
    },
    {
        path: '/sandbox',
        name: 'Sandbox',
        component: () => import('../views/SandboxView.vue'),
        meta: { requiresAuth: true }
    },
    {
        path: '/mcp',
        name: 'MCP',
        component: () => import('../views/MCPView.vue'),
        meta: { requiresAuth: true }
    },
    {
        path: '/presets',
        name: 'Presets',
        component: () => import('../views/PresetsView.vue'),
        meta: { requiresAuth: true }
    },
    {
        path: '/config',
        name: 'Config',
        component: () => import('../views/ConfigView.vue'),
        meta: { requiresAuth: true }
    },
    {
        path: '/tools',
        name: 'Tools',
        component: () => import('../views/ToolsView.vue'),
        meta: { requiresAuth: true }
    },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

// 路由守卫
router.beforeEach((to, _from, next) => {
    const authStore = useAuthStore()

    if (to.meta.requiresAuth && !authStore.isAuthenticated) {
        next({ name: 'Login' })
    } else if (to.name === 'Login' && authStore.isAuthenticated) {
        next({ name: 'Dashboard' })
    } else {
        next()
    }
})

export default router

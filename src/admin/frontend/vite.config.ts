import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: path.resolve(__dirname, '../static'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8088',
        changeOrigin: true,
      },
      // Handle WebSocket upgrades efficiently
      '/api/logs/stream': {
        target: 'ws://localhost:8088',
        ws: true,
        changeOrigin: true,
      },
      '/api/sandbox/ws': {
        target: 'ws://localhost:8088',
        ws: true,
        changeOrigin: true,
      }
    }
  }
})

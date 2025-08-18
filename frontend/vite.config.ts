import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
      target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
    define: {},
  }
})

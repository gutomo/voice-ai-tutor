import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// 開発時はフロント (:5173) からの /api/* を FastAPI (:8000) へプロキシする。
// 本番は FastAPI が同一オリジンで SPA を配信するため、CORS は不要。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

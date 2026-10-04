import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true, // Fail if port 5173 is already in use instead of choosing another port
    // Proxy backend API calls with extended timeout for long-running LLM requests
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 500000, // 500s — allows LLM requests up to ~450s (backend's default 180s + buffer)
      }
    }
  },
})


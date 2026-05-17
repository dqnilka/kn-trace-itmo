import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
    },
    // Allow opening /api/v1/exams/.../viewer in a new tab without CORS surprises.
  },
})

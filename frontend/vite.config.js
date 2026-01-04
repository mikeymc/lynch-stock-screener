import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  appType: 'spa', // Enables SPA fallback for client-side routing
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || `http://localhost:${process.env.VITE_API_PORT || '8080'}`,
        changeOrigin: true,
      }
    }
  }
})

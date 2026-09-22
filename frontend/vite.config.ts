import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy the two backend routes to FastAPI in dev so the app makes
    // same-origin requests (no CORS, no hardcoded port in the client).
    proxy: {
      '/chat': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/transcribe': 'http://localhost:8000',
      '/speak': 'http://localhost:8000',
    },
  },
})

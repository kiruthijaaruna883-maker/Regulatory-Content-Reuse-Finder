import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/regulatory': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/content': 'http://127.0.0.1:8000',
      '/documents': 'http://127.0.0.1:8000',
      '/review': 'http://127.0.0.1:8000',
      '/changes': 'http://127.0.0.1:8000',
      '/history': 'http://127.0.0.1:8000',
    },
  },
})

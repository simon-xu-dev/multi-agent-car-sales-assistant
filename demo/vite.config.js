import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: '/multi-agent-car-sales-assistant/demo/',
  plugins: [react(), tailwindcss()],
})

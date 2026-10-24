import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In development the dashboard is served by Vite (http://localhost:5173) and the browser asks Vite for the data.
// Vite forwards these paths to the FastAPI server, so the browser only ever talks to ONE address and CORS never
// comes into play. In production there is no Vite: FastAPI serves the built files itself (see main.py).
const API = 'http://127.0.0.1:8000'
const API_PATHS = ['health', 'products', 'recalls', 'analytics', 'insights', 'reports', 'search', 'stats', 'docs', 'openapi.json']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(API_PATHS.map((path) => [`/${path}`, { target: API }])),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.js',
    css: false,
  },
})

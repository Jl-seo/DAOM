/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['react', 'react-dom', 'axios'],
          'pdf-viewer': ['@react-pdf-viewer/core', '@react-pdf-viewer/highlight', 'pdfjs-dist'],
          'ui': ['lucide-react', 'clsx', 'sonner'],
        }
      }
    }
  }
})

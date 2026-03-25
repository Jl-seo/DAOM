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
          'vendor': ['react', 'react-dom'],
          'pdf-viewer': ['react-pdf', 'pdfjs-dist'],
          'ui': ['lucide-react', 'clsx', 'sonner', '@radix-ui/react-dialog', '@radix-ui/react-popover'],
          'table': ['@tanstack/react-table'],
          'query': ['@tanstack/react-query', 'axios'],
        }
      }
    }
  }
})

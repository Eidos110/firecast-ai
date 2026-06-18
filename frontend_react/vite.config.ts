import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Force apache-arrow to use browser build
      'apache-arrow': resolve(__dirname, 'node_modules/apache-arrow/Arrow.dom.js')
    }
  },
  base: './',  // Use relative paths for assets (required for Streamlit components)
  build: {
    outDir: 'build',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]'
      }
    }
  },
  server: {
    port: 3000
  }
})